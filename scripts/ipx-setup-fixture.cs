using System;using System.IO;using Microsoft.Win32;using Amagadon;
class Test {
 static void Require(bool value,string message){if(!value)throw new Exception(message);}
 static int Main(string[] args) {
  string path=@"Software\AmagadonSetupFixture-"+Guid.NewGuid().ToString("N"),backup=Path.Combine(args[0],"ipx-setup-test.json");
  try {using(var root=Registry.CurrentUser.CreateSubKey(path)) {
   bool rejected=false;try{IpxSetup.Register(root,backup);}catch(IOException){rejected=true;}Require(rejected,"Missing DirectPlay accepted");
   using(var key=root.CreateSubKey(@"SOFTWARE\Microsoft\DirectPlay\Service Providers\TCP fixture")){key.SetValue("Guid","other");key.SetValue("Path","untouched.dll");}
   var added=IpxSetup.Register(root,backup);Require(added.Length==2,"Missing keys not added");
   using(var key=root.OpenSubKey(@"SOFTWARE\Microsoft\DirectPlay\Service Providers\IPX Connection For DirectPlay")) {Require((string)key.GetValue("Guid")=="{685BC400-9D2C-11CF-A9CD-00AA006886E3}","Wrong IPX GUID");Require((int)key.GetValue("dwReserved1")==50,"Wrong provider flags");}
   using(var key=root.OpenSubKey(@"SOFTWARE\Microsoft\DirectPlay\Services\{5146ab8cb6b1ce11920c00aa006c4972}"))Require(key.GetValueKind("Path")==RegistryValueKind.ExpandString,"Wrong service path kind");
   Require(IpxSetup.Register(root,backup).Length==0,"Registration not idempotent");
   using(var key=root.OpenSubKey(@"SOFTWARE\Microsoft\DirectPlay\Service Providers\TCP fixture"))Require((string)key.GetValue("Path")=="untouched.dll","Other provider modified");
   using(var key=root.OpenSubKey(@"SOFTWARE\Microsoft\DirectPlay\Service Providers\IPX Connection For DirectPlay",true))key.SetValue("Path","custom.dll");
   rejected=false;try{IpxSetup.Register(root,backup);}catch(IOException){rejected=true;}Require(rejected,"Custom provider overwritten");
  }File.WriteAllText(Path.Combine(args[0],"ipx-setup-pass.txt"),"PASS: missing DirectPlay rejection, missing IPX registration, schema and registry types, idempotence, unrelated provider preservation, custom path protection; isolated HKCU only, system DirectPlay untouched");return 0;
  }catch(Exception ex){File.WriteAllText(Path.Combine(args[0],"ipx-setup-error.txt"),ex.ToString());return 1;}
  finally {Registry.CurrentUser.DeleteSubKeyTree(path,false);}
 }
}
