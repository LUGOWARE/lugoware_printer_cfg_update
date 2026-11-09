import ipaddress,json,os,re,sys
from pathlib import Path
import paramiko

def run(request):
    host=str(ipaddress.ip_address(request['host']))
    user=request.get('user','biqu')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*',user):raise ValueError('Invalid SSH user')
    action=request.get('action','check')
    command='python3 /home/biqu/.local/share/lugoware/factory_reset.py --check'
    if action=='reset':
        identity=request.get('machine_id','')
        if not re.fullmatch(r'[a-f0-9]{32}',identity):raise ValueError('Reconnect before reset')
        command='python3 /home/biqu/.local/share/lugoware/factory_reset.py --reset --confirm '+identity
    elif action!='check':raise ValueError('Invalid operation')
    cache=Path(os.environ['LOCALAPPDATA'])/'LugowareFactory';cache.mkdir(parents=True,exist_ok=True)
    known=cache/'known_hosts';client=paramiko.SSHClient()
    if known.exists():client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host,port=int(request.get('port',22)),username=user,password=request['password'],
                       allow_agent=False,look_for_keys=False,timeout=12,auth_timeout=12,banner_timeout=12)
        client.save_host_keys(str(known))
        stdin,stdout,stderr=client.exec_command(command,timeout=180)
        data=stdout.read().decode('utf-8');error=stderr.read().decode('utf-8',errors='replace')
        code=stdout.channel.recv_exit_status()
        try:result=json.loads(data)
        except ValueError:raise RuntimeError('Printer initialization tool is unavailable or returned an invalid response.')
        if code:raise RuntimeError(result.get('error','Factory command failed'))
        return result
    finally:client.close()

def main():
    try:
        request=json.loads(sys.stdin.buffer.readline(65536).decode('utf-8-sig'))
        result=run(request);code=0
    except paramiko.AuthenticationException:
        result={'error':'SSH 인증 실패: 아이디와 비밀번호를 확인하세요.'};code=1
    except paramiko.BadHostKeyException:
        result={'error':'프린터의 SSH 식별키가 변경되었습니다. 기기를 확인해 주세요.'};code=1
    except Exception as exc:
        result={'error':str(exc)};code=1
    sys.stdout.buffer.write((json.dumps(result,ensure_ascii=False)+'\n').encode('utf-8'));sys.stdout.buffer.flush()
    return code
if __name__=='__main__':sys.exit(main())
