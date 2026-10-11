import struct,pathlib,json
root=pathlib.Path(__file__).resolve().parents[3]; inv=json.loads((root/'docs/research/inventory.json').read_text(encoding='utf8'))
END=0xfffffffe
for rec in inv:
 if not rec['path'].endswith('.doc'):continue
 if pathlib.Path(rec['path']).name.startswith('~$'):rec['status']='office_lock_file';continue
 b=(root/rec['path']).read_bytes();u32=lambda x,o:struct.unpack_from('<I',x,o)[0];sec=1<<struct.unpack_from('<H',b,30)[0];ms=1<<struct.unpack_from('<H',b,32)[0]
 def sector(i):return b[(i+1)*sec:(i+2)*sec]
 dif=list(struct.unpack_from('<109I',b,76)); di=u32(b,68)
 for k in range(u32(b,72)):
  ar=struct.unpack('<%dI'%(sec//4),sector(di));dif.extend(ar[:-1]);di=ar[-1]
 fat=[]
 for i in dif:
  if i<0xfffffffa:fat.extend(struct.unpack('<%dI'%(sec//4),sector(i)))
 def chain(i,tab):
  seen=set();out=[]
  while i<0xfffffffa and i not in seen:
   seen.add(i);out.append(i);i=tab[i]
  return out
 def stream(i,size):return b''.join(sector(x) for x in chain(i,fat))[:size]
 directory=stream(u32(b,48),10**8); entries={};rootentry=None
 for off in range(0,len(directory),128):
  e=directory[off:off+128]
  if len(e)<128:continue
  n=struct.unpack_from('<H',e,64)[0];name=e[:max(0,n-2)].decode('utf-16le',errors='replace');typ=e[66];start=u32(e,116);size=struct.unpack_from('<Q',e,120)[0]
  if typ==5:rootentry=(start,size)
  elif typ==2:entries[name]=(start,size)
 mini=stream(*rootentry);mfraw=stream(u32(b,60),u32(b,64)*sec);mf=list(struct.unpack('<%dI'%(len(mfraw)//4),mfraw))
 def read(name):
  i,size=entries[name]
  if size>=u32(b,56):return stream(i,size)
  return b''.join(mini[x*ms:(x+1)*ms] for x in chain(i,mf))[:size]
 word=read('WordDocument');table=read('1Table' if struct.unpack_from('<H',word,10)[0]&512 else '0Table');fc=u32(word,0x1a2);cb=u32(word,0x1a6);clx=table[fc:fc+cb];at=0
 while clx[at]==1:at+=3+struct.unpack_from('<H',clx,at+1)[0]
 assert clx[at]==2
 length=u32(clx,at+1);plc=clx[at+5:at+5+length];n=(length-4)//12;cps=struct.unpack_from('<%dI'%(n+1),plc,0);parts=[]
 for i in range(n):
  f=u32(plc,4*(n+1)+8*i+2);count=cps[i+1]-cps[i]
  if f&0x40000000:pos=(f&0x3fffffff)//2;parts.append(word[pos:pos+count].decode('cp1251',errors='replace'))
  else:pos=f&0x3fffffff;parts.append(word[pos:pos+2*count].decode('utf-16le',errors='replace'))
 text=''.join(parts).replace('\r','\n');out=root/'docs/research/extracted'/(rec['id']+'.txt');out.write_text(text,encoding='utf8');rec['status']='legacy_word_piece_table_extracted';rec['characters']=len(text);rec['extracted_text']=out.relative_to(root).as_posix();rec['limitations']='Embedded Equation Editor objects and figures are not decoded.'
 print(rec['id'],len(text),repr(text[:1300]))
(root/'docs/research/inventory.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2),encoding='utf8')
