param([switch]$Preview)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object Windows.Forms.Form
$form.Text='LUGOWARE 공장 출고 초기화';$form.Size=New-Object Drawing.Size(680,580);$form.StartPosition='CenterScreen'
$form.BackColor=[Drawing.Color]::FromArgb(28,28,28);$form.ForeColor=[Drawing.Color]::White
$form.Font=New-Object Drawing.Font('맑은 고딕',10)
function Label($text,$x,$y){$c=New-Object Windows.Forms.Label;$c.Text=$text;$c.Location=New-Object Drawing.Point($x,$y);$c.AutoSize=$true;$form.Controls.Add($c)}
function TextBox($x,$y,$width){$c=New-Object Windows.Forms.TextBox;$c.Location=New-Object Drawing.Point($x,$y);$c.Width=$width;$form.Controls.Add($c);return $c}
function Button($text,$x,$y,$width){$c=New-Object Windows.Forms.Button;$c.Text=$text;$c.Location=New-Object Drawing.Point($x,$y);$c.Size=New-Object Drawing.Size($width,40);$c.FlatStyle='Flat';$form.Controls.Add($c);return $c}
Label '프린터 IP' 20 22;$ip=TextBox 150 18 250
Label 'SSH 사용자' 20 64;$user=TextBox 150 60 250;$user.Text='biqu'
Label 'SSH 비밀번호' 20 108;$password=TextBox 150 104 370;$password.UseSystemPasswordChar=$true
$remember=New-Object Windows.Forms.CheckBox;$remember.Text='이 PC에 아이디·비밀번호 저장 (Windows 계정 암호화)';$remember.Location=New-Object Drawing.Point(20,150);$remember.Size=New-Object Drawing.Size(610,28);$form.Controls.Add($remember)
$connect=Button '연결 확인' 20 190 180;$reset=Button '프린터 초기화' 220 190 180;$reset.Enabled=$false
$log=New-Object Windows.Forms.TextBox;$log.Location=New-Object Drawing.Point(20,245);$log.Size=New-Object Drawing.Size(620,270);$log.Multiline=$true;$log.ReadOnly=$true;$log.ScrollBars='Vertical';$form.Controls.Add($log)
$script:plan=$null;$script:process=$null;$script:operation=''
$cache=Join-Path $env:LOCALAPPDATA 'LugowareFactory';[IO.Directory]::CreateDirectory($cache)|Out-Null
$settings=Join-Path $cache 'credentials.json'
function Save-Credentials {
 if($remember.Checked){
  $secure=ConvertTo-SecureString $password.Text -AsPlainText -Force
  @{user=$user.Text;password=($secure|ConvertFrom-SecureString)}|ConvertTo-Json|Set-Content -Encoding UTF8 -LiteralPath $settings
 }else{if(Test-Path -LiteralPath $settings){Remove-Item -LiteralPath $settings}}
}
$remember.Add_CheckedChanged({if(-not $remember.Checked -and (Test-Path -LiteralPath $settings)){Remove-Item -LiteralPath $settings}})
try{
 if(Test-Path -LiteralPath $settings){
  $saved=Get-Content -LiteralPath $settings -Raw|ConvertFrom-Json
  $secure=ConvertTo-SecureString $saved.password
  $user.Text=$saved.user;$password.Text=([Net.NetworkCredential]::new('',$secure)).Password;$remember.Checked=$true
 }
}catch{$log.Text='저장된 인증정보를 읽지 못했습니다. 다시 입력해 주세요.'}
foreach($field in @($ip,$user,$password)){$field.Add_TextChanged({$reset.Enabled=$false;$script:plan=$null})}
function Start-Remote($operation){
 $parsed=$null
 if(-not [Net.IPAddress]::TryParse($ip.Text.Trim(),[ref]$parsed)){throw '올바른 IP 주소를 입력하세요.'}
 if($user.Text -notmatch '^[a-z_][a-z0-9_-]*$'){throw 'SSH 사용자 이름을 확인하세요.'}
 if(-not $password.Text){throw 'SSH 비밀번호를 입력하세요.'}
 $extra='--check'
 if($operation -eq 'reset'){
  if(-not $script:plan -or $script:plan.machine_id -notmatch '^[a-f0-9]{32}$'){throw '연결 확인이 필요합니다.'}
  $extra='--reset --confirm '+$script:plan.machine_id
 }
 $payload=@{host=$ip.Text.Trim();user=$user.Text;password=$password.Text;action=$operation}
 if($operation -eq 'reset'){$payload.machine_id=$script:plan.machine_id}
 $psi=New-Object Diagnostics.ProcessStartInfo;$psi.FileName=Join-Path $PSScriptRoot 'FactorySSH.exe'
 $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardInput=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
 $psi.StandardOutputEncoding=[Text.Encoding]::UTF8;$psi.StandardErrorEncoding=[Text.Encoding]::UTF8
 $script:process=New-Object Diagnostics.Process;$script:process.StartInfo=$psi
 [void]$script:process.Start();$script:outTask=$script:process.StandardOutput.ReadToEndAsync();$script:errTask=$script:process.StandardError.ReadToEndAsync()
 $bytes=[Text.Encoding]::UTF8.GetBytes(($payload|ConvertTo-Json -Compress)+"`n")
 $script:process.StandardInput.BaseStream.Write($bytes,0,$bytes.Length);$script:process.StandardInput.Close()
 $payload.password=$null;[Array]::Clear($bytes,0,$bytes.Length)
 $script:operation=$operation;$connect.Enabled=$false;$reset.Enabled=$false;$ip.Enabled=$false;$user.Enabled=$false;$password.Enabled=$false;$remember.Enabled=$false
 $log.Text=if($operation -eq 'reset'){'출고 초기화 중입니다. 전원을 끄지 마세요.'}else{'프린터 연결 및 초기화 대상 확인 중...'}
}
$connect.Add_Click({try{Start-Remote 'check'}catch{$log.Text=$_.Exception.Message}})
$reset.Add_Click({
 $message="대상: $($ip.Text)`r`nG-code: $($script:plan.gcode_files)개 / 누적 출력: $($script:plan.history_count)회`r`n`r`nG-code, 썸네일, 이력·통계, 복구·점검 기록을 삭제합니다.`r`n설정·보정값·네트워크 정보는 유지됩니다.`r`n삭제한 데이터는 되돌릴 수 없습니다. 진행할까요?"
 if([Windows.Forms.MessageBox]::Show($message,'출고 초기화 확인','YesNo','Warning') -eq 'Yes'){try{Start-Remote 'reset'}catch{$log.Text=$_.Exception.Message}}
})
$timer=New-Object Windows.Forms.Timer;$timer.Interval=250
$timer.Add_Tick({
 if($script:process -and $script:process.HasExited){
  $stdout=$script:outTask.Result;$stderr=$script:errTask.Result;$exit=$script:process.ExitCode;$script:process.Dispose();$script:process=$null
  $connect.Enabled=$true;$ip.Enabled=$true;$user.Enabled=$true;$password.Enabled=$true;$remember.Enabled=$true
  try{
   $result=$stdout|ConvertFrom-Json
   if($exit -ne 0){throw ($result.error+' '+$stderr)}
   if($script:operation -eq 'check'){
    $script:plan=$result;$reset.Enabled=[bool]$result.ready;Save-Credentials
    $log.Text="연결 성공: $($result.hostname)`r`n기기 ID: $($result.machine_id)`r`nG-code: $($result.gcode_files)개`r`n누적 출력: $($result.history_count)회`r`n`r`n삭제: G-code·썸네일·출력 기록·통계·복구·점검 기록`r`n보존: 기구 설정·보정값·Wi-Fi·펌웨어`r`n"
    if(-not $result.ready){$log.AppendText("`r`n현재 초기화 불가: "+($result.reasons -join ', '))}
   }else{$script:plan=$null;$log.Text='초기화 완료. 프린터에 최초 설정 화면이 표시됩니다. 출고 전에는 설정을 완료하지 말고 정상 종료하세요.'}
  }catch{$log.Text="실패: $($_.Exception.Message)`r`n$stdout`r`n$stderr";$script:plan=$null}
 }
})
$form.Add_FormClosing({param($sender,$event) if($script:process){$event.Cancel=$true;[void][Windows.Forms.MessageBox]::Show('작업 완료 후 창을 닫아 주세요.')}})
if($Preview){
 $form.StartPosition="Manual";$form.Location=New-Object Drawing.Point(-10000,-10000);$form.Show();[Windows.Forms.Application]::DoEvents();$bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height);$form.DrawToBitmap($bitmap,$form.ClientRectangle);$bitmap.Save((Join-Path $PSScriptRoot 'preview.png'));$bitmap.Dispose();$form.Dispose()
}else{$timer.Start();[void]$form.ShowDialog();$timer.Dispose()}
