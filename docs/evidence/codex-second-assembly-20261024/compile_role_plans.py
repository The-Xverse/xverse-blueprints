from pathlib import Path
import hashlib,json,os,sys
sys.path.insert(0,os.getcwd())
import check_topology as C
import topology as T
schemas=C.schemas(Path(os.environ["XVERSE_PLATFORM_PROFILES"]))
rows=[]
for arm in T.ARMS:
 for form in T.FORMS:
  documents=C.load(arm,form)
  validation,result=C.compile_docs(documents,schemas)
  assert validation.is_valid and result.is_valid,(arm,form)
  rows.append(dict(arm=arm,form=form,semanticDigest=result.plan["digest"],sourceDigests={name:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest() for name,value in documents.items()}))
out=Path(__file__).with_name("compiled-role-plan-digests.json")
out.write_text(json.dumps(rows,indent=2)+"\n")
print(str(len(rows))+" genuine compiled plan digests recorded")
