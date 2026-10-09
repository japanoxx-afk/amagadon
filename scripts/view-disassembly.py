import pathlib,sys
lines=(pathlib.Path(__file__).resolve().parent.parent/'analysis/raw/disassembly.txt').read_text().splitlines()
start=int(sys.argv[1],16); end=int(sys.argv[2],16)
print('\n'.join(line for line in lines if start<=int(line[:8],16)<end))
