using System;using System.IO;using System.Linq;using System.Net;using System.Net.Http;using System.Threading;using System.Threading.Tasks;using System.Web.Script.Serialization;using Amagadon;
class Fixture {
 class Handler:HttpMessageHandler {
  public string Json,Hash;public byte[] Zip;public int Requests;public bool FailDownload,MissingRelease;public CancellationTokenSource CancelDownload;
  protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token){
   token.ThrowIfCancellationRequested();Requests++;var response=new HttpResponseMessage(HttpStatusCode.OK);
   if(r.RequestUri.AbsoluteUri==Updates.LatestUrl){if(MissingRelease)response.StatusCode=HttpStatusCode.NotFound;response.Content=new StringContent(Json);}
   else if(r.RequestUri.AbsolutePath.EndsWith(".sha256"))response.Content=new StringContent(Hash);
   else {if(CancelDownload!=null){CancelDownload.Cancel();token.ThrowIfCancellationRequested();}if(FailDownload)response.StatusCode=HttpStatusCode.ServiceUnavailable;response.Content=new ByteArrayContent(Zip);}
   return Task.FromResult(response);
  }
 }
 static void Require(bool value,string message){if(!value)throw new Exception(message);}
 static string Metadata(string version){return "{\"tag_name\":\""+version+"\",\"draft\":false,\"prerelease\":false,\"assets\":[{\"name\":\"AmagadonLauncher.zip\",\"browser_download_url\":\"https://github.com/japanoxx-afk/amagadon/releases/download/"+version+"/AmagadonLauncher.zip\"},{\"name\":\"AmagadonLauncher.zip.sha256\",\"browser_download_url\":\"https://github.com/japanoxx-afk/amagadon/releases/download/"+version+"/AmagadonLauncher.zip.sha256\"}]}";}
 static async Task Run(string root) {
  string seed=Path.Combine(root,"seed.zip");File.WriteAllBytes(seed,new byte[]{1,2,3,4});string digest=Core.Hash(seed);
  // Reproduce the exact 0.3.9 cast before verifying the typed replacement.
  var raw=new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(Metadata("v99.0.0"));
  bool reproduced=false;try{var broken=(object[])raw["assets"];}catch(InvalidCastException){reproduced=true;}Require(reproduced,"Old ArrayList regression not reproduced");
  Require(Updates.Parse(Metadata("v99.0.0")).assets.Length==2,"typed assets failed");
  foreach(string scenario in new[]{"startup-accept","manual-accept","cancel","latest","older","not-published","missing","duplicate","untrusted","bad-hash","http-error","cancel-token","cancel-download","draft","bad-version"}) {
   var handler=new Handler {Json=Metadata("v99.0.0"),Hash=digest,Zip=File.ReadAllBytes(seed)};int confirmations=0;bool rejected=false;string result=null;
   if(scenario=="latest")handler.Json=Metadata("v0.3.9");if(scenario=="older")handler.Json=Metadata("v0.3.8");
   if(scenario=="missing")handler.Json=handler.Json.Replace("AmagadonLauncher.zip.sha256","missing.txt");
   if(scenario=="not-published")handler.MissingRelease=true;
   if(scenario=="duplicate"){var release=Updates.Parse(handler.Json);release.assets=release.assets.Concat(new[]{release.assets[0]}).ToArray();handler.Json=new JavaScriptSerializer().Serialize(release);}
   if(scenario=="untrusted")handler.Json=handler.Json.Replace("https://github.com/","https://example.com/");
   if(scenario=="bad-hash")handler.Hash=new string('0',64);
   if(scenario=="http-error")handler.FailDownload=true;
   if(scenario=="draft")handler.Json=handler.Json.Replace("\"draft\":false","\"draft\":true");
   if(scenario=="bad-version")handler.Json=Metadata("v99.0.0-preview");
   using(var cts=new CancellationTokenSource())using(var client=new HttpClient(handler)) {
    if(scenario=="cancel-token")cts.Cancel();
    if(scenario=="cancel-download")handler.CancelDownload=cts;
    try{result=await Updates.Prepare(client,"0.3.9",Path.Combine(root,scenario),r=>{confirmations++;return scenario!="cancel";},s=>{},cts.Token);}catch(Exception){rejected=true;}
   }
   bool success=scenario.EndsWith("accept"),quiet=scenario=="cancel" || scenario=="latest" || scenario=="older" || scenario=="not-published";
   Require(rejected==(!success && !quiet),"Wrong outcome: "+scenario);
   if(success)Require(result!=null && Core.Hash(result)==digest && confirmations==1 && handler.Requests==3,"Download failed: "+scenario);
   else Require(result==null && !Directory.GetFiles(root,"*.partial",SearchOption.AllDirectories).Any(),"Partial package left: "+scenario);
   if(quiet)Require(handler.Requests==1 && confirmations==(scenario=="cancel"?1:0),"Unexpected confirmation/download: "+scenario);
  }
 }
 static int Main(string[] args){try {
  if(args[0]=="handoff") {
   Updates.StartInstaller(args[1],args[2],Path.GetFileName(System.Reflection.Assembly.GetExecutingAssembly().Location),System.Diagnostics.Process.GetCurrentProcess().Id,CancellationToken.None).GetAwaiter().GetResult();
   File.WriteAllText(Path.Combine(args[2],"parent-ready.txt"),"ready");Thread.Sleep(1200);return 0;
  }
  if(args[0]=="preflight-failure") {
   bool failed=false;try {Updates.StartInstaller(args[1],args[2],"AmagadonLauncher.exe",System.Diagnostics.Process.GetCurrentProcess().Id,CancellationToken.None).GetAwaiter().GetResult();}catch(IOException){failed=true;}
   Require(failed,"Corrupt archive accepted");File.WriteAllText(Path.Combine(args[2],"preflight-rejected.txt"),"alive");return 0;
  }
  if(args[0]=="live") {
   ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
   using(var client=new HttpClient()) {
    client.DefaultRequestHeaders.UserAgent.ParseAdd("AmagadonLauncher-update-test/0.3.12");int confirmations=0;
    string package=Updates.Prepare(client,"0.0.1",args[1],r=>{confirmations++;return true;},s=>{},CancellationToken.None).GetAwaiter().GetResult();
    Require(confirmations==1 && package!=null && File.Exists(package),"Live download failed");
    File.WriteAllText(Path.Combine(args[1],"live-pass.txt"),"PASS: public GitHub latest metadata, typed assets, release ZIP download and SHA256 validation");return 0;
   }
  }
  Run(args[1]).GetAwaiter().GetResult();File.WriteAllText(Path.Combine(args[1],"client-pass.txt"),"PASS: 0.3.9 ArrayList reproduction; typed release; shared startup/manual path; confirm/cancel; current/older; missing asset; bad URL/hash; HTTP failure; cancellation; draft/version rejection");return 0;
 }catch(Exception ex){File.WriteAllText(Path.Combine(Path.GetTempPath(),"Amagadon-update-fixture-error.txt"),ex.ToString());return 1;}}
}
