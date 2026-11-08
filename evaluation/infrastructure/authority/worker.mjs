import { DurableObject } from 'cloudflare:workers';
import { Ledger } from './ledger.mjs';
import { ProviderLedger } from './provider-ledger.mjs';

async function authorized(request, secret) {
  if (typeof secret !== 'string' || secret.length < 32) return false;
  const supplied=request.headers.get('Authorization') ?? '';
  const hash = async value => new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));
  const [a,b]=await Promise.all([hash(supplied),hash('Bearer '+secret)]);
  let diff=0; for(let i=0;i<a.length;i++) diff |= a[i]^b[i]; return diff===0;
}
export class SessionAuthority extends DurableObject {
  constructor(ctx,env) {
    super(ctx,env);
    this.ledger=new Ledger(ctx.storage,{authority_id:env.AUTHORITY_ID,incarnation:env.AUTHORITY_INCARNATION});
    this.providers=new ProviderLedger(ctx.storage,this.ledger,env.PROVIDER_ISSUER);
    this.env=env;
  }
  async fetch(request) {
    const url=new URL(request.url);
    const operator=url.pathname.startsWith('/operator/');
    const provider=/^\/v1\/provider\/(enroll|check|revoke|inspect|constrain)$/.exec(url.pathname)?.[1];
    // pgsql-http follows POST redirects unconditionally. HEAD does not follow
    // them, and carries only a bounded nonce-bound request/response header.
    const head=request.method==='HEAD' && ['check','revoke','inspect','constrain'].includes(provider);
    const credential=provider ? ({enroll:this.env.PROVIDER_ENROLL_TOKEN,
      check:this.env.PROVIDER_CHECK_TOKEN,revoke:this.env.PROVIDER_REVOKE_TOKEN,constrain:this.env.PROVIDER_REVOKE_TOKEN,
      inspect:this.env.PROVIDER_CHECK_TOKEN})[provider] : operator ? this.env.OPERATOR_TOKEN : this.env.APPLICATION_TOKEN;
    if (provider) {
      const tokens=[this.env.APPLICATION_TOKEN,this.env.OPERATOR_TOKEN,this.env.PROVIDER_ENROLL_TOKEN,
        this.env.PROVIDER_CHECK_TOKEN,this.env.PROVIDER_REVOKE_TOKEN];
      if(tokens.some(t=>typeof t!=='string'||t.length<32)||new Set(tokens).size!==tokens.length)
        return new Response(null,{status:503});
    }
    if (this.env.APPLICATION_TOKEN === this.env.OPERATOR_TOKEN) return new Response(null,{status:503});
    if ((request.method!=='POST' && !head) || url.search || !(await authorized(request,credential)))
      return new Response(null,{status:403});
    try {
      let body;
      if(head) {
        const raw=request.headers.get('X-RosaGo-Request');
        if(!raw || raw.length>4096) throw new Error();
        body=JSON.parse(raw);
      } else {
      const reader=request.body?.getReader(); if (!reader) throw new Error();
      const chunks=[];let size=0;
      for (;;) { const {value,done}=await reader.read();if(done)break;size+=value.length;
        if(size>65536){await reader.cancel();throw new Error();}chunks.push(value); }
      const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
      body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      }
      let result;
      if(provider) result=this.providers.exchange(provider,body);
      else if(url.pathname==='/operator/initialize') result=this.ledger.initialize(body);
      else if(url.pathname==='/operator/block') result=this.ledger.block();
      else if(url.pathname==='/v1/authority') result=this.ledger.exchange(body);
      else return new Response(null,{status:404});
      if(head) return new Response(null,{headers:{'Cache-Control':'no-store',
        'X-RosaGo-Result':JSON.stringify(result)}});
      return Response.json(result,{headers:{'Cache-Control':'no-store'}});
    } catch {return new Response(null,{status:503,headers:{'Cache-Control':'no-store'}});}
  }
}
export default {
  async fetch(request,env) {
    // Object selection is operator configuration, never a client parameter.
    const url=new URL(request.url);
    if (url.protocol!=='https:' && !(env.LOCAL_TEST_ONLY==='true' && ['127.0.0.1','localhost'].includes(url.hostname)))
      return new Response(null,{status:403});
    if (!['/v1/authority','/operator/initialize','/operator/block',
      '/v1/provider/enroll','/v1/provider/check','/v1/provider/revoke','/v1/provider/inspect',
      '/v1/provider/constrain'].includes(url.pathname)) return new Response(null,{status:404});
    const id=env.AUTHORITY.idFromName(env.AUTHORITY_OBJECT);
    // Deliberately no retry wrapper, especially around commits.
    return env.AUTHORITY.get(id).fetch(request);
  }
};
