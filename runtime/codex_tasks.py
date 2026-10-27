"""Local, single-task Codex launcher; browser requests never supply shell commands."""
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager

ACTIVE = {'starting', 'running', 'stopping'}


def job_comments(job):
    # Keep earlier single-comment task records readable after this upgrade.
    return job.get('comments') or ([job['comment']] if job.get('comment') else [])


def batch_key(comments):
    return sorted((c['id'], c['updatedAt']) for c in comments)


def write_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


@contextmanager
def mailbox(directory):
    # Serialize delivery with a worker's final queue check and lock release.
    with (directory / 'mailbox.lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def inbox_messages(directory):
    return sorted((json.loads(p.read_text()) for p in (directory / 'inbox').glob('*.json')),
                  key=lambda m: (m['createdAt'], m['id']))


def find_codex():
    found = shutil.which('codex')
    if found:
        return found
    # Finder launchers have a smaller PATH than the IDE terminal.
    extensions = Path.home() / '.vscode/extensions'
    candidates = list(extensions.glob('openai.chatgpt-*/bin/*/codex'))
    for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def resolve_executable(executable):
    """Bare names use PATH; configured filesystem paths never fall back elsewhere."""
    if not executable:
        return None
    value = str(executable)
    if '/' not in value:
        found = shutil.which(value)
        return str(Path(found).resolve()) if found else None
    path = Path(value).resolve()
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def skill_path():
    return Path(__file__).resolve().parent.parent / 'skills' / 'web-review' / 'SKILL.md'


def execution_config_for(config):
    # Deliberately whitelist execution fields; configuration must never carry credentials.
    codex = {'approvalPolicy': 'never', 'sandbox': 'danger-full-access'}
    if config.codex.get('model'):
        codex['model'] = config.codex['model']
    return {'projectId': config.project_id, 'toolVersion': config.tool_version,
            'guidance': copy.deepcopy(config.guidance), 'codex': codex,
            'skillPath': str(skill_path())}


class TaskConflict(Exception):
    pass


class CodexTasks:
    def __init__(self, project, data, output, executable=None, execution_config=None):
        self.project = Path(project).resolve()
        self.data = Path(data).resolve()
        self.output = Path(output).resolve()
        self.executable = resolve_executable(executable) if executable is not None else find_codex()
        self.execution_config = copy.deepcopy(execution_config)
        self.output.mkdir(parents=True, exist_ok=True)
        self.mutex = threading.Lock()
        self.workers = []

    def _lock(self):
        handle = (self.output / 'active.lock').open('a+')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            handle.close()
            return None

    def current(self):
        try:
            identity = json.loads((self.output / 'current.json').read_text())['id']
            if not isinstance(identity, str) or not identity.isalnum():
                return None
            path = self.output / identity / 'status.json'
            job = json.loads(path.read_text())
        except (OSError, ValueError, KeyError):
            return None
        if job['status'] in ACTIVE:
            handle = self._lock()
            if handle:
                # A crashed worker must not leave the UI claiming it is still working.
                try:
                    job = json.loads(path.read_text())
                    if job['status'] in ACTIVE:
                        job.update(status='failed', error='任务意外中断，可重试；已经完成的修改仍保留。', finishedAt=time.time())
                        write_json(path, job)
                finally:
                    handle.close()
        self.workers = [p for p in self.workers if p.poll() is None]
        try:
            reviews = {c['id']: c for c in json.loads((self.data / 'comments.json').read_text())}
        except (OSError, ValueError):
            reviews = {}
        job['comments'] = [{**c, 'reviewStatus': reviews.get(c['id'], {}).get('status', 'unknown')}
                           for c in job_comments(job)]
        job['completedCount'] = sum(c['reviewStatus'] in ('changed', 'resolved') for c in job['comments'])
        job['pendingCount'] = sum(c['reviewStatus'] == 'open' for c in job['comments'])
        job['messages'] = sorted(job.get('messages', []) + inbox_messages(path.parent),
                                 key=lambda m: (m['createdAt'], m['id']))
        job['canChat'] = bool(job.get('threadId') or job['status'] in ACTIVE)
        return job

    def status(self):
        return {'available': bool(self.executable and os.access(self.executable, os.X_OK)),
                'reason': '' if self.executable and os.access(self.executable, os.X_OK) else '未检测到本机 Codex，请安装或在启动服务时指定 --codex-bin。',
                'job': self.current()}

    def _spawn(self, directory, handle):
        with (directory / 'worker.log').open('ab') as log:
            worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(directory), str(handle.fileno())],
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                      pass_fds=(handle.fileno(),), start_new_session=True)
        self.workers.append(worker)

    def start(self, comments, review_url, retry_job_id=None):
        with self.mutex:
            if not self.status()['available']:
                raise ValueError('未检测到可执行的本机 Codex')
            previous = self.current()
            if previous and previous['status'] in ACTIVE:
                return previous
            if retry_job_id and (not previous or previous['id'] != retry_job_id):
                raise TaskConflict('任务已变化，请刷新后再重试。')
            comments = sorted(comments, key=lambda c: c['number'])
            if not comments:
                raise TaskConflict('没有待处理评论，请刷新查看。')
            same = previous and batch_key(job_comments(previous)) == batch_key(comments)
            if same and previous['status'] == 'completed' and not retry_job_id:
                return previous
            if self.execution_config:
                path = Path(self.execution_config['skillPath'])
                if not path.is_absolute() or not path.is_file() or not os.access(path, os.R_OK):
                    raise ValueError('web-review skill 不可读；请检查固定版本安装。')
            handle = self._lock()
            if not handle:
                raise TaskConflict('已有 Codex 任务在处理评论，请等待完成或先停止该任务。')
            job = {'id': uuid.uuid4().hex, 'status': 'starting',
                   'comments': [{key: c[key] for key in ('id', 'number', 'text', 'updatedAt')} for c in comments],
                   'startedAt': time.time(), 'finishedAt': None, 'progress': '正在启动 Codex',
                   'result': '', 'error': '', 'threadId': None, 'messages': [], 'transport': 'app-server'}
            directory = self.output / job['id']
            directory.mkdir()
            try:
                write_json(directory / 'status.json', job)
                request = {'project': str(self.project), 'data': str(self.data),
                           'reviewUrl': review_url, 'executable': self.executable, 'comments': comments}
                if self.execution_config is not None:
                    request['executionConfig'] = copy.deepcopy(self.execution_config)
                write_json(directory / 'request.json', request)
                self._spawn(directory, handle)
                write_json(self.output / 'current.json', {'id': job['id']})
            except OSError:
                job.update(status='failed', error='无法启动本机 Codex，请检查安装与目录权限。', finishedAt=time.time())
                write_json(directory / 'status.json', job)
                raise ValueError(job['error'])
            finally:
                handle.close()
            return job

    def message(self, identity, message_id, text):
        if not isinstance(message_id, str) or len(message_id) != 32 or any(c not in '0123456789abcdef' for c in message_id):
            raise ValueError('消息编号无效')
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('请输入 1–4000 字的消息')
        with self.mutex:
            job = self.current()
            if not job or job['id'] != identity:
                raise TaskConflict('当前任务已变化，消息尚未发送，请核对后再试。')
            directory = self.output / identity
            with mailbox(directory):
                job = json.loads((directory / 'status.json').read_text())
                folder = directory / 'inbox'; folder.mkdir(exist_ok=True)
                path = folder / (message_id + '.json')
                if path.exists():
                    previous = json.loads(path.read_text())
                    if previous['text'] != text.strip():
                        raise TaskConflict('消息编号已用于其他内容')
                    return self.current()
                if job['status'] == 'stopping' or (directory / 'cancel').exists() and job['status'] in ACTIVE:
                    raise TaskConflict('任务正在停止，请停止后再继续对话。')
                if not job.get('threadId') and job['status'] not in ACTIVE:
                    raise TaskConflict('任务尚未建立会话，请重试未完成项。')
                if job.get('transport') != 'app-server' and job['status'] in ACTIVE:
                    raise TaskConflict('旧版任务正在执行，请结束后继续对话。')
                handle = self._lock()
                message = {'id': message_id, 'role': 'user', 'text': text.strip(),
                           'createdAt': time.time(), 'status': 'queued'}
                write_json(path, message)
                try:
                    if handle:
                        # Resume the same persisted Codex thread, including legacy exec tasks.
                        if not job.get('messages') and job.get('result'):
                            job['messages'] = [{'id': 'previous-result', 'role': 'assistant', 'text': job['result'],
                                                'createdAt': job.get('finishedAt') or job['startedAt']}]
                        job.update(status='starting', progress='正在继续对话', error='', finishedAt=None, transport='app-server')
                        (directory / 'cancel').unlink(missing_ok=True)
                        write_json(directory / 'status.json', job)
                        self._spawn(directory, handle)
                except OSError:
                    message.update(status='failed', error='会话启动失败，消息未发送，请重新发送。')
                    write_json(path, message)
                    job.update(status='failed', error=message['error'], finishedAt=time.time())
                    write_json(directory / 'status.json', job)
                    raise ValueError(message['error'])
                finally:
                    if handle:
                        handle.close()
            return self.current()

    def stop(self, identity):
        with self.mutex:
            job = self.current()
            if not job or job['id'] != identity:
                raise TaskConflict('任务已变化，请刷新后再试。')
            if job['status'] in ACTIVE:
                (self.output / identity / 'cancel').touch()
            return job


def legacy_prompt_for(request):
    return f'''用户从 Morsea 本机评审工具栏点击「交给 Codex」，授权你一次性处理以下批次中的全部待处理评论。
项目目录：{request['project']}
评审入口：{request['reviewUrl']}
评论数据目录：{request['data']}
本次评论快照（共 {len(request['comments'])} 条，按编号从旧到新）：
{json.dumps(request['comments'], ensure_ascii=False, indent=2)}

执行要求：
1. 先读取 AGENTS.md、README.md、docs/design/README.md 和 docs/current-state.md，再通读本批次全部评论及每条评论的原截图、锚点与全部附图。截图和附图路径由评论数据目录下的 screenshots/ 与 attachments/ 对应 URL 获取。
2. 按编号及依赖关系逐条处理本批次，不遗漏旧的待处理评论，也不加入运行期间新增的评论。每条开始前通过 /__review/comments 核对当前记录；状态不再 open 或正文、附图、updatedAt 已与快照不一致时跳过该条并说明，继续其余评论。以当前设计规范和用户后续明确确认的要求为准，不因旧评论恢复已被替换的设计；无法判断的冲突保留 open。
3. 直接完成任务范围内的可逆修改和必要脚本，不再询问脚本执行权限。页面源码只改 prototype/，保留已有未提交修改及草稿规则；不提交、推送或部署，不启动其他 Codex 或子代理，不调用本任务启动接口。
4. 修改后构建，按改动范围使用隔离浏览器和临时评论数据验证；准确报告通过、失败或未完成事项。逐条汇报正在处理的评论编号。
5. 每条评论完成并验证后才标记 changed，不能标记 resolved，也不能因为批次结束将未完成的评论一并标记。首次更新前完整备份评论目录；每次更新前重新读取当前记录，核对仍与快照一致，使用最新 updatedAt 作为 expectedUpdate POST 到 /__review/comments，保留原截图、锚点、附图和其他评论，写清 resolution。若该条需要产品决策或没有完成，保持 open，继续其他可独立处理的评论。
6. 用中文返回批次结果，列明已完成和未完成的评论编号、改了什么、实际验证及如何查看。不要把进程结束或测试通过当作全部评论完成或用户验收。
'''


def prompt_for(request):
    execution = request.get('executionConfig')
    if execution is None:
        return legacy_prompt_for(request)
    guidance = execution.get('guidance', {})
    return f'''你是本机网页评审派发的独立 worker，直接处理当前冻结批次，不要递归启动评审任务、其他 Codex 或子代理。
项目目录：{request['project']}
项目标识：{execution.get('projectId', '')}
工具版本：{execution.get('toolVersion', '')}
评审入口：{request['reviewUrl']}
评论数据目录：{request['data']}
项目必读文件：{json.dumps(guidance.get('requiredFiles', []), ensure_ascii=False)}
允许修改的源码范围：{json.dumps(guidance.get('sourceRoots', []), ensure_ascii=False)}
构建命令（argv）：{json.dumps(guidance.get('buildCommands', []), ensure_ascii=False)}
检查命令（argv）：{json.dumps(guidance.get('checkCommands', []), ensure_ascii=False)}
本次评论快照（共 {len(request['comments'])} 条，按编号从旧到新）：
{json.dumps(request['comments'], ensure_ascii=False, indent=2)}

执行要求：
1. 先读取项目 AGENTS.md（如有）、上述必读文件及 web-review skill，检查本批次原截图、锚点和全部附图；不要套用其他项目规范。源码范围和命令由项目配置定义；缺失或冲突时保留相关评论 open 并说明，不臆造构建成功。
2. 按编号及依赖处理冻结批次，不加入运行期间新增评论。每条开始前 GET 评审入口的 __review/comments 核对原记录；状态不再 open 或正文、附图、updatedAt 与快照不一致时跳过该条并说明，继续其他独立评论。
3. 直接完成范围内的可逆修改，保留已有未提交修改；不提交、推送、部署或调用任务启动接口。首次更新前完整备份评论目录至项目外部，保留全部原证据及时间戳。
4. 构建并按修改范围使用隔离浏览器和临时数据检查，准确报告实际通过、失败和未执行的检查。逐条汇报评论编号。
5. 仅完成且验证后标记 changed，不能标记 resolved。更新前重新读取记录且核对冻结快照，以最新 updatedAt 为 expectedUpdate POST 到 __review/comments，带本机评审 Origin，保留原截图、锚点、附件及其他字段，写清 resolution 并回读。不覆盖冲突、不重复处理已变更的评论；未完成保持 open。
6. 中文返回每条已完成、跳过或未完成的结果、验证和查看方式。进程结束不等于评论完成或用户验收。
'''


def run_worker(directory, lock_fd):
    from codex_session import run_session
    run_session(directory, lock_fd, prompt_for)


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != '--worker':
        raise SystemExit('Use the local review server to start tasks.')
    run_worker(Path(sys.argv[2]).resolve(), int(sys.argv[3]))
