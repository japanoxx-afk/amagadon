using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.Linq;using System.Threading.Tasks;using Microsoft.Win32;
namespace Amagadon {
 public static class IpxSetup {
  const string Providers=@"SOFTWARE\Microsoft\DirectPlay\Service Providers";
  const string Provider=Providers+@"\IPX Connection For DirectPlay";
  const string Service=@"SOFTWARE\Microsoft\DirectPlay\Services\{5146ab8cb6b1ce11920c00aa006c4972}";
  const string Guid="{685BC400-9D2C-11CF-A9CD-00AA006886E3}";
  public static void CheckFiles(string folder) {
   Core.Validate(folder);Core.EnsureIdle(folder);
   foreach(string name in new[]{"ipxwrapper.dll","dpwsockx.dll","wsock32.dll","mswsock.dll"}) {
    string file=Path.Combine(folder,name);
    if(!File.Exists(file))throw new IOException("IPXWrapper 파일이 없습니다: "+name+". 공식 IPXWrapper 전체 DLL을 게임 폴더에 설치한 후 다시 시도해주세요.");
    using(var input=File.OpenRead(file))if(input.Length<64 || input.ReadByte()!=0x4d || input.ReadByte()!=0x5a)throw new IOException("올바른 DLL 파일이 아닙니다: "+name);
   }
  }
  // Registry schema matches IPXWrapper's official DirectPlay setup. Only
  // absent keys are added; existing providers and paths are never overwritten.
  public static string[] Register(RegistryKey root,string backup) {
   string existing=null;
   using(var providers=root.OpenSubKey(Providers)) {
    if(providers==null)throw new IOException("DirectPlay 등록이 없습니다. Windows 기능의 레거시 구성 요소에서 DirectPlay를 먼저 활성화해주세요.");
    foreach(string name in providers.GetSubKeyNames())using(var key=providers.OpenSubKey(name))if(String.Equals(key.GetValue("Guid") as string,Guid,StringComparison.OrdinalIgnoreCase)){existing=Providers+"\\"+name;break;}
   }
   var created=new List<string>();
   if(existing==null) {using(var collision=root.OpenSubKey(Provider))if(collision!=null)throw new IOException("동일한 이름의 다른 공급자가 있어 변경하지 않았습니다.");created.Add(Provider);}
   else using(var key=root.OpenSubKey(existing))if(!String.Equals(key.GetValue("Path") as string,"dpwsockx.dll",StringComparison.OrdinalIgnoreCase))throw new IOException("기존 IPX 공급자가 별도 경로를 사용하므로 자동 변경하지 않았습니다.");
   using(var service=root.OpenSubKey(Service)) {
    if(service==null)created.Add(Service);
    else if(!String.Equals(service.GetValue("Path") as string,"dpwsockx.dll",StringComparison.OrdinalIgnoreCase))throw new IOException("기존 IPX 서비스가 별도 경로를 사용하므로 자동 변경하지 않았습니다.");
   }
   Directory.CreateDirectory(Path.GetDirectoryName(backup));
   File.WriteAllText(backup,Core.Json.Serialize(new {time=DateTime.Now.ToString("o"),registryView="Registry32",previouslyAbsent=created.ToArray(),note="Only these previously absent keys are added; no existing values or game files are changed."}));
   var touched=new List<string>();
   try {
    foreach(string path in created)using(var key=root.CreateSubKey(path)) {
     touched.Add(path);key.SetValue("Path","dpwsockx.dll",path==Service?RegistryValueKind.ExpandString:RegistryValueKind.String);
     if(path==Provider) {key.SetValue("Guid",Guid);key.SetValue("DescriptionA","IPX Connection For DirectPlay");key.SetValue("DescriptionW","IPX Connection For DirectPlay");key.SetValue("dwReserved1",50,RegistryValueKind.DWord);key.SetValue("dwReserved2",0,RegistryValueKind.DWord);}
     else key.SetValue("Description","WinSock IPX Connection For DirectPlay");
    }
   }catch {foreach(string path in touched)try{root.DeleteSubKeyTree(path,false);}catch{}throw;}
   return created.ToArray();
  }
  public static int Repair(string folder) {
   try {CheckFiles(folder);string backup=Path.Combine(Core.Home,"NetworkSetup",DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+".json");
    using(var root=RegistryKey.OpenBaseKey(RegistryHive.LocalMachine,RegistryView.Registry32)) {var added=Register(root,backup);Core.Log("IPX registration repaired; added="+String.Join(",",added)+" backup="+backup);}return 0;
   }catch(Exception ex){Core.Log("IPX registration repair failed: "+ex);System.Windows.Forms.MessageBox.Show(ex.Message,"IPX 등록 복구 실패");return 1;}
  }
  public static async Task RunElevated(string folder) {
   CheckFiles(folder);
   using(var p=Process.Start(new ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location,"--repair-ipx \""+Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar)+"\""){UseShellExecute=true,Verb="runas",WindowStyle=ProcessWindowStyle.Hidden})) {
    await Task.Run(()=>p.WaitForExit());if(p.ExitCode!=0)throw new IOException("IPX 등록을 복구하지 못했습니다. 표시된 오류와 로깅 리포트를 확인해주세요.");
   }
  }
 }
}
