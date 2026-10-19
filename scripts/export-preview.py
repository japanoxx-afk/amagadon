"""Export our patch recipe only; never distribute the game's executable or assets."""
import pathlib, sys, json, hashlib, gzip, base64
original = pathlib.Path(sys.argv[1]).read_bytes()
patched_path = pathlib.Path(sys.argv[2])
patched = patched_path.read_bytes()
manifest = json.loads(patched_path.with_suffix('.probe.json').read_text())
if hashlib.sha256(original).hexdigest() != manifest['supported_hash']:
    raise ValueError('Original hash does not match the probe manifest')
verification=json.loads((patched_path.parent/'probe-verification.json').read_text())
if verification['executable_hash'] != hashlib.sha256(patched).hexdigest():
    raise ValueError('Run verify-probe.py against this build before exporting')
edits=[];i=0
while i<len(original):
    if original[i]==patched[i]:i+=1;continue
    start=i
    while i<len(original) and original[i]!=patched[i]:i+=1
    edits.append({'Offset':start,'Before':original[start:i].hex(),'After':patched[start:i].hex()})
recipe={'Version':'0.3.2-preview','ReleaseCandidate':False,
    'InputHash':manifest['supported_hash'],'InputLength':len(original),
    'OutputHash':hashlib.sha256(patched).hexdigest(),'OutputLength':len(patched),
    'Edits':edits,'AppendGzip':base64.b64encode(gzip.compress(patched[len(original):],mtime=0)).decode(),
    'Stages':manifest['stages'],'VerifiedChecks':verification['checks']}
destination=pathlib.Path(__file__).resolve().parent.parent/'compat/hd-preview.json'
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(recipe,indent=2)+'\n',encoding='utf8')
print('Recipe SHA256',hashlib.sha256(destination.read_bytes()).hexdigest())
