from collections import namedtuple
import struct,requests
import sys, time
from elasticsearch import Elasticsearch, exceptions as es_exceptions

header = namedtuple("header", ["code", "pseq","plen","server_start"])
mapheader = namedtuple("mapheader",["dictID","info"])

userid   = namedtuple("userid",["username","pid","sid","host"])
authinfo = namedtuple("authinfo",["ap","dn","hn","on","rn","gn","info","inetv"])
srvinfo  = namedtuple("srvinfo",["program","version","instance","port","site","addr"])
prginfo  = namedtuple("prginfo",["xfn","tod","sz","at","ct","mt","fn"])
xfrinfo  = namedtuple("xfrinfo",["lfn","tod","sz","tm","op","rc","pd"])

fileOpen  = namedtuple("fileOpen", ["rectype","recFlag","recSize","fileID", "fileSize","userID","fileName"])
fileXfr   = namedtuple("fileXfr",  ["rectype","recFlag","recSize","fileID","read","readv","write"])
fileClose = namedtuple("fileClose",["rectype","recFlag","recSize","fileID","read","readv","write","ops"])
fileTime  = namedtuple("fileTime", ["rectype","recFlag","recSize","isXfr_recs","total_recs","sid","reserved","tBeg","tEnd"])
fileDisc  = namedtuple("fileDisc", ["rectype","recFlag","recSize","userID"])
ops       = namedtuple("ops",["read","readv","write","rsMin","rsMax","rsegs","rdMin","rdMax","rvMin","rvMax","wrMin","wrMax"])

def userInfo(message):
    c = message
    if '/' in message:
        prot,c = message.split('/',1)
    hind = c.rfind('@')
    host = c[hind+1:]
    c=c[:hind]
    c,sid = c.split(':',1)
    hind = c.rfind('.')
    pid = c[hind+1:]
    user = c[:hind]
    pi=0
    si=0
    try:
        pi=int(pid)
        si=int(sid)
    except ValueError as e: 
        print("serious value error: ", pid, sid, "message was:", message)
    return userid(user,pi,si,host)

def authorizationInfo(message):
    r=message.split('&')
    ap=dn=hn=on=rn=gn=m=inetv=''
    for i in r:
        kv=i.split('=')
        if len(kv)==2:
            if kv[0]=='p':   ap=kv[1]
            elif kv[0]=='n': dn=kv[1]
            elif kv[0]=='h': hn=kv[1]
            elif kv[0]=='o': on=kv[1]
            elif kv[0]=='r': rn=kv[1]
            elif kv[0]=='g': gn=kv[1]
            elif kv[0]=='m': m =kv[1]
            elif kv[0]=='I': inetv =kv[1]
    return authinfo(ap,dn,hn,on,rn,gn,m,inetv)

def serverInfo(message, addr):
    r=message.split('&')
    pgm =r[1].split('=')[1]
    ver =r[2].split('=')[1]
    inst=r[3].split('=')[1]
    port=r[4].split('=')[1]
    site=r[5].split('=')[1]
    return srvinfo(pgm,ver,inst,port,site, addr)
    
def purgeInfo(message):
    xfn,rest=message.split('\n')
    r=rest.split("&")
    tod=r[1].split('=')[1]
    sz =r[2].split('=')[1]
    at =r[3].split('=')[1]
    ct =r[4].split('=')[1]
    mt =r[5].split('=')[1]
    fn =r[6].split('=')[1]
    return prginfo(xfn,tod,sz,at,ct,mt,fn)

def xfrInfo(message):
    lfn, rest==message.split('\n')
    r=rest.split("&")
    tod=r[1].split('=')[1]
    sz =r[2].split('=')[1]
    tm =r[3].split('=')[1]
    op =r[4].split('=')[1]
    rc =r[5].split('=')[1]
    if (len(r)==7):
        pd =r[6].split('=')[1]
    else:
        pd = ''
    return  xfrinfo([lfn,tod,sz,tm,op,rc,pd])
    
def MonFile(d):
    up=struct.unpack("!BBHI",d[:8]) # XrdXrootdMonHeader
    
    if up[0]==0: # isClose
        O = ()
        if up[1] & 0b010:  #hasOPS
            O=ops._make(struct.unpack("!IIIHHQIIIIII",d[32:80]))
        #forced Disconnect prior to close  forced =0x01, hasOPS =0x02, hasSSQ =0x04
        unpacked = struct.unpack("!BBHIQQQ",d[:32])
        unpacked = unpacked + (O,)
        return fileClose._make(unpacked)
    elif up[0]==1: # isOpen
        fO=struct.unpack("!BBHIQ",d[:16])
        if up[1]==1:
            userId=struct.unpack("!I",d[16:20])[0]
            fileName=struct.unpack("!"+str(up[2]-20)+"s",d[20:up[2]])[0].rstrip('\0')
        else:
            userId=0
            fileName=''
        return fileOpen._make(fO + (userId,fileName))
    elif up[0]==2: # isTime
        if up[2]==16: # this and next 3 lines can be removed after the fixed montiring stream is deployed.
            t = struct.unpack("!BBHHHII",d[:16])
            return fileTime(t[0],t[1],t[2],t[3],t[4],0,0,t[5],t[6])
        else:
            return fileTime._make(struct.unpack("!BBHHHIIII",d[:24]))
    elif up[0]==3: #isXfr
        # print "isXfr ..."
        return fileXfr._make(struct.unpack("!BBHIQQQ",d[:32]))
    else: # isDisc up[0]==4
        return fileDisc._make(up)
    
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
AllCoordinates={}
def getLongLat(IP):
    return None
    if IP in AllCoordinates:
        return AllCoordinates[IP]
    try:
        res = requests.get('http://geoip.mwt2.org:4288/json/'+IP)
        if res.status_code==200:
            r=res.json()
            lon=r['longitude']
            lat=r['latitude']
            print(r['country_name'], r['city'], [lon,lat])
            AllCoordinates[IP]=[lon,lat]
            return [lon,lat]
    except:
        print("# Can't determine client coordinates using geoip.mwt2.org ", sys.exc_info()[0])
            
