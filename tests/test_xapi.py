from pathlib import Path
from xwasm.xapi import read, validate_manifest
def test_seed_xapi_valid():
    root=Path(__file__).resolve().parents[1]
    data=read(root/"specs/xapi/v1.seed.json")
    assert data["format"]=="xwasm-xapi"
    assert "KERNEL32.dll" in data["libraries"]
def test_rejects_arbitrary_bridge():
    data={"format":"xwasm-xapi","version":1,"libraries":{"K.dll":{"functions":{"F":{"id":1,"abi":"stdcall","args":[],"return":"u32","bridge":"javascript.eval"}}}}}
    assert any("bridge" in e for e in validate_manifest(data))
