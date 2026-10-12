// Supplemental checks, reported separately from the frozen requirement score.
// Usage: node extra_checks.mjs OUTPUT_DIR PLAYWRIGHT_PATH [browser-channel, default chrome]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require=createRequire(import.meta.url);
const [outputRoot,playwrightPath,channel='chrome']=process.argv.slice(2);
const {chromium}=require(playwrightPath);
// Cases come from the protocol; historical two-arm runs used "<scenario>-<arm>".
const protocol=JSON.parse(fs.readFileSync(path.join(outputRoot,'protocol.json'),'utf8'));
const cases=(scenario)=>protocol.order.filter(e=>e[0]===scenario).map(e=>e.length===3?`${e[0]}-${e[1]}-r${e[2]}`:`${e[0]}-${e[1]}`);
const checks=[];
async function check(caseName,name,fn){try{await fn();checks.push({case:caseName,name,passed:true});}catch(e){checks.push({case:caseName,name,passed:false,error:String(e.stack||e)});}}
for(const caseName of cases('app')){
  const mod=await import(pathToFileURL(path.join(outputRoot,'cases',caseName,'snapshot-2','board.js')).href);
  await check(caseName,'Editing cannot replace the stable task id',()=>{
    const b=mod.createBoard(),t=mod.addTask(b,{title:'Original'}),id=t.id;
    mod.editTask(b,id,{id:'replaced',title:'Updated'});assert.equal(b.tasks[0].id,id);
  });
  await check(caseName,'Stale restored counter creates 100 unique subsequent ids',()=>{
    const b=mod.createBoard();for(let i=0;i<10;i++)mod.addTask(b,{title:'Existing '+i});
    const data=JSON.parse(mod.serialize(b));data.nextId=1;
    const restored=mod.restore(JSON.stringify(data));assert.equal(restored.tasks.length,10);
    for(let i=0;i<100;i++)assert.ok(mod.addTask(restored,{title:'New '+i}));
    assert.equal(new Set(restored.tasks.map(t=>t.id)).size,110);
  });
}
const browser=await chromium.launch({channel,headless:true});
try{
  for(const caseName of cases('game')){
    const root=path.join(outputRoot,'cases',caseName,'snapshot-2');
    const server=http.createServer((req,res)=>{
      const u=new URL(req.url,'http://localhost'),f=path.resolve(root,'.'+(u.pathname==='/'?'/index.html':decodeURIComponent(u.pathname)));
      if(!f.startsWith(root+path.sep)){res.writeHead(403).end();return;}
      try{res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[path.extname(f)]||'text/plain');res.end(fs.readFileSync(f));}catch{res.writeHead(404).end();}
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();page.setDefaultTimeout(4000);
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    try{
      await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForTimeout(100);
      await check(caseName,'Complete a game with keyboard and persist best score across reload',async()=>{
        // Discover the actual UI deck through keyboard play, then restart.
        // UI IDs/symbols may differ from the module fixture while satisfying the contract.
        const ids=await page.locator('[data-card-id]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-card-id')));
        const pairs=new Map();
        for(let i=0;i<ids.length;i+=2){
          for(const id of ids.slice(i,i+2)){
            const card=page.locator('[data-card-id="'+id+'"]');
            await card.focus();await page.keyboard.press('Enter');
            const face=card.locator('.card-face,.card-symbol');
            const symbol=(await (await face.count()===1?face:card).innerText()).trim();
            if(!pairs.has(symbol))pairs.set(symbol,[]);pairs.get(symbol).push(id);
          }
          await page.waitForTimeout(950);
        }
        assert.equal(pairs.size,4);for(const pair of pairs.values())assert.equal(pair.length,2);
        await page.locator('#restart').click();
        for(const pair of pairs.values())for(const id of pair){await page.locator('[data-card-id="'+id+'"]').focus();await page.keyboard.press('Enter');}
        assert.match(await page.locator('#game-status').innerText(),/won|win|complete|congrat|found all four pairs/i);
        assert.match(await page.locator('#moves').innerText(),/\b4\b/);assert.match(await page.locator('#best-score').innerText(),/\b4\b/);
        assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('memory-best'))),4);
        await page.screenshot({path:path.join(outputRoot,'cases',caseName,'victory.png'),fullPage:true});
        await page.reload();assert.match(await page.locator('#best-score').innerText(),/\b4\b/);assert.deepEqual(errors,[]);
      });
      await check(caseName,'Malformed best-score storage recovers without script failure',async()=>{
        await page.evaluate(()=>localStorage.setItem('memory-best','malformed'));await page.reload();assert.equal(await page.locator('[data-card-id]').count(),8);assert.deepEqual(errors,[]);
      });
    }finally{await context.close();await new Promise(resolve=>server.close(resolve));}
  }
}finally{await browser.close();}
fs.writeFileSync(path.join(outputRoot,'extra-checks.json'),JSON.stringify({checks,passed:checks.filter(c=>c.passed).length,total:checks.length},null,2)+'\n');
console.log(JSON.stringify(checks));
