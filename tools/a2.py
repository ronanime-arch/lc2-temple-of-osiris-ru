import mul
d,ents=mul.entries()
tot=0; bad=[]
for nm,e in sorted(ents.items()):
    ch=mul.chunks(d,e); ns=mul.nstreams(d,e,ch)
    for si in range(ns):
        sl=mul.slots(d,e,si,ch)
        buf=b''.join(d[o:o+mul.SLOT] for o in sl)
        good=sum(1 for k in range(0,len(buf),mul.SLOT) if mul.issync(buf,k))
        res=max([mul.mdb(buf[k:k+8]) for k in range(0,len(buf),mul.SLOT) if mul.issync(buf,k)] or [-1])
        if good!=e['frames'] or res!=0:
            bad.append((nm,si,good,e['frames'],res))
        tot+=1
print('проверено потоков: %d, расхождений: %d'%(tot,len(bad)))
for b in bad[:10]: print('  ',b)
