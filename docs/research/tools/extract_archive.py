import pathlib,json,hashlib,zipfile,xml.etree.ElementTree as ET,fitz
root=pathlib.Path(__file__).resolve().parents[3]
out=root/'docs'/'research'/'extracted';out.mkdir(parents=True,exist_ok=True)
records=[]
for p in sorted(list((root/'papers').rglob('*'))+list((root/'Свидетельства').rglob('*'))):
 if not p.is_file(): continue
 rid='L%02d'%(len(records)+1); raw=p.read_bytes(); rec=dict(id=rid,path=p.relative_to(root).as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 try:
  if p.suffix.lower()=='.pdf':
   d=fitz.open(p); pages=[page.get_text(sort=True) for page in d]; rec['pages']=len(d);rec['page_characters']=[len(t.strip()) for t in pages];rec['metadata']=d.metadata;text='\n\n'.join('=== PDF page %d ===\n%s'%(i+1,t) for i,t in enumerate(pages));rec['status']='text_extracted' if len(text)>100 else 'needs_ocr'
  elif p.suffix.lower()=='.docx':
   z=zipfile.ZipFile(p);el=ET.fromstring(z.read('word/document.xml')); ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'};text='\n'.join(''.join(x.text or '' for x in e.iter() if x.tag in ('{'+ns['w']+'}t','{'+ns['m']+'}t')) for e in el.findall('.//w:p',ns));rec['status']='ooxml_text_extracted'
  elif p.suffix.lower()=='.py':text=raw.decode('utf8');rec['status']='source_read'
  else:rec['status']='binary_pending';text=''
  if text:
   f=out/(rid+'.txt');f.write_text(text,encoding='utf8');rec['extracted_text']=f.relative_to(root).as_posix();rec['characters']=len(text)
 except Exception as e:rec['status']='extraction_error';rec['error']=str(e)
 records.append(rec)
(root/'docs'/'research'/'inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(records,ensure_ascii=False,indent=2))
