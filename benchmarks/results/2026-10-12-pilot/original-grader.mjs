import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const [workspace, scenario, stageText, output, playwrightPath] = process.argv.slice(2);
const stage = Number(stageText), groups = [];
const require = createRequire(import.meta.url);
const { chromium } = require(playwrightPath);
let api, moduleError;
try { api = await import(pathToFileURL(path.join(workspace, {website:'catalogue.js',game:'game.js',app:'board.js'}[scenario])).href); }
catch (error) { moduleError = error; }
async function test(id, name, fn) {
  try { await fn(); groups.push({id,name,passed:true}); }
  catch (error) { groups.push({id,name,passed:false,error:String(error.stack || error).slice(0,2200)}); }
}
function core(id,name,fn) { return test(id,name,()=>{ if(moduleError)throw moduleError; return fn(); }); }
const clone = x => JSON.parse(JSON.stringify(x));
const ids = x => x.map(a=>a.id);
const rows = scenario==='website'?JSON.parse(fs.readFileSync(path.join(workspace,'workshops.json'))):null;
const deck = Array.from({length:8},(_,i)=>({id:String(i+1),symbol:String.fromCharCode(65+Math.floor(i/2))}));

if(scenario==='website') {
  await core('W1','Combined search/category/price filters',()=>{
    assert.deepEqual(ids(api.filterWorkshops(rows,{query:'  prAGue ',category:'photo',maxPrice:40,sort:'title'})),['w6']);
    assert.deepEqual(ids(api.filterWorkshops(rows,{query:'łÓDŹ',category:'all',maxPrice:null,sort:'title'})),['w4']);
    assert.equal(api.filterWorkshops(rows,{query:'absent',category:'all',maxPrice:'',sort:'title'}).length,0);
  });
  await core('W2','Stable sorting and immutable source',()=>{
    const copy=clone(rows); const sorted=api.filterWorkshops(rows,{query:'',category:'all',maxPrice:null,sort:'price-asc'});
    assert.deepEqual(ids(sorted),['w4','w1','w6','w2','w3','w5']);
    assert.deepEqual(ids(api.filterWorkshops(rows,{sort:'price-desc'})),['w5','w2','w3','w1','w6','w4']);
    assert.deepEqual(rows,copy);
    assert.deepEqual(ids(api.filterWorkshops(rows,{maxPrice:40,sort:'title'})),['w1','w6','w4']);
  });
  await core('W3','Booking validation rejects invalid fields',()=>{
    const ok=api.validateBooking({name:'  Ana ',email:'ana@example.com',workshopId:'w1'},rows);
    assert.equal(ok.valid,true);assert.deepEqual(ok.errors,{});
    const bad=api.validateBooking({name:'  ',email:'no-at-sign',workshopId:'missing'},rows);
    assert.equal(bad.valid,false);assert.deepEqual(Object.keys(bad.errors).sort(),['email','name','workshopId']);
  });
  if(stage===2) {
    await core('W7','Shortlist toggle validates ids without mutation',()=>{
      const input=['w1','w1'];assert.deepEqual(api.toggleShortlist(input,'w2',rows),['w1','w2']);assert.deepEqual(input,['w1','w1']);
      assert.deepEqual(api.toggleShortlist(['w1','w2'],'w1',rows),['w2']);
      assert.deepEqual(api.toggleShortlist(['w1'],'missing',rows),['w1']);
    });
    await core('W8','Shortlist corrupt storage is recovered safely',()=>{
      assert.deepEqual(api.loadShortlist('["w1","bad","w1","w4"]',rows),['w1','w4']);
      for(const raw of ['bad','{}','null','42'])assert.deepEqual(api.loadShortlist(raw,rows),[]);
    });
    await core('W9','URL filter round trip and invalid-value defaults',()=>{
      const f={query:'Clay & café',category:'pottery',maxPrice:0,sort:'price-desc'};
      assert.deepEqual(api.decodeFilters(api.encodeFilters(f)),f);
      assert.deepEqual(api.decodeFilters('?query=x&category=bad&maxPrice=-1&sort=bad'),{query:'x',category:'all',maxPrice:null,sort:'title'});
      assert.equal(api.decodeFilters('?maxPrice=NaN').maxPrice,null);
      assert.deepEqual(api.decodeFilters(''),{query:'',category:'all',maxPrice:null,sort:'title'});
    });
  }
}
if(scenario==='game') {
  await core('G1','Initial state copies the supplied deck',()=>{
    const original=clone(deck),s=api.createGame(deck);
    assert.equal(s.cards.length,8);assert.equal(s.moves,0);assert.equal(s.matched,0);assert.equal(s.locked,false);assert.equal(s.status,'playing');assert.deepEqual(s.selected,[]);
    assert.ok(s.cards.every(c=>c.faceUp===false&&c.matched===false));assert.deepEqual(deck,original);assert.notEqual(s.cards,deck);
  });
  await core('G2','Pair match and invalid duplicate flips',()=>{
    const s=api.createGame(deck);assert.equal(api.flip(s,'bad'),false);assert.equal(api.flip(s,'1'),true);assert.equal(api.flip(s,'1'),false);
    assert.equal(s.moves,0);assert.equal(api.flip(s,'2'),true);assert.equal(s.moves,1);assert.equal(s.matched,1);assert.deepEqual(s.selected,[]);assert.equal(s.locked,false);
    assert.ok(s.cards.filter(c=>['1','2'].includes(c.id)).every(c=>c.matched&&c.faceUp));assert.equal(api.flip(s,'1'),false);
  });
  await core('G3','Mismatch lock, resolution and move count',()=>{
    const s=api.createGame(deck);api.flip(s,'1');api.flip(s,'3');assert.equal(s.locked,true);assert.equal(s.moves,1);assert.equal(api.flip(s,'5'),false);
    api.resolveMismatch(s);assert.equal(s.locked,false);assert.deepEqual(s.selected,[]);assert.ok(s.cards.every(c=>!c.faceUp));assert.equal(s.moves,1);
    api.resolveMismatch(s);assert.equal(s.moves,1);
  });
  await core('G4','Win and full restart reset',()=>{
    const s=api.createGame(deck);for(const c of deck)api.flip(s,c.id);assert.equal(s.status,'won');assert.equal(s.matched,4);assert.equal(s.moves,4);
    const reversed=clone(deck).reverse();api.restart(s,reversed);assert.deepEqual(ids(s.cards),ids(reversed));assert.equal(s.status,'playing');assert.equal(s.moves,0);assert.equal(s.matched,0);assert.equal(s.locked,false);assert.deepEqual(s.selected,[]);
    assert.ok(s.cards.every(c=>!c.faceUp&&!c.matched));assert.ok(reversed.every(c=>!Object.hasOwn(c,'faceUp')));
  });
  if(stage===2) {
    await core('G8','Paused state prevents flips and mismatch resolution',()=>{
      const s=api.createGame(deck);assert.equal(s.paused,false);api.flip(s,'1');api.flip(s,'3');api.pause(s);assert.equal(s.paused,true);
      const snapshot=clone(s);assert.equal(api.flip(s,'5'),false);api.resolveMismatch(s);assert.deepEqual(s,snapshot);
      api.resume(s);api.resolveMismatch(s);assert.equal(s.paused,false);assert.equal(s.locked,false);assert.deepEqual(s.selected,[]);
      api.pause(s);api.restart(s,deck);assert.equal(s.paused,false);
    });
    await core('G9','Best score only updates for a completed valid game',()=>{
      assert.equal(api.updateBest(null,7,'won'),7);assert.equal(api.updateBest(7,5,'won'),5);assert.equal(api.updateBest(5,8,'won'),5);assert.equal(api.updateBest(5,5,'won'),5);
      for(const score of [0,-2,1.5,NaN,'4'])assert.equal(api.updateBest(5,score,'won'),5);
      assert.equal(api.updateBest(null,4,'playing'),null);assert.equal(api.updateBest(5,4,'playing'),5);assert.equal(api.updateBest('broken',4,'won'),4);
    });
  }
}
if(scenario==='app') {
  await core('A1','Add task defaults, stable ids and invalid input',()=>{
    const b=api.createBoard();assert.deepEqual(b.tasks,[]);assert.equal(b.nextId,1);
    const a=api.addTask(b,{title:'  Alpha  '}),c=api.addTask(b,{title:'Beta',priority:'high'});
    assert.equal(a.title,'Alpha');assert.equal(a.status,'todo');assert.equal(a.priority,'medium');assert.equal(typeof a.id,'string');assert.notEqual(a.id,c.id);
    const before=clone(b);for(const input of [{title:' '},{title:'X',priority:'bad'},{title:'X',status:'bad'}])assert.equal(api.addTask(b,input),false);assert.deepEqual(b,before);
  });
  await core('A2','Atomic edit, move and delete validation',()=>{
    const b=api.createBoard(),t=api.addTask(b,{title:'Alpha'});assert.equal(api.editTask(b,t.id,{title:' Edited ',priority:'low'}),true);assert.equal(b.tasks[0].title,'Edited');assert.equal(b.tasks[0].id,t.id);
    const before=clone(b);assert.equal(api.editTask(b,t.id,{title:'Lost',priority:'bad'}),false);assert.deepEqual(b,before);
    assert.equal(api.moveTask(b,t.id,'done'),true);assert.equal(b.tasks[0].status,'done');assert.equal(api.moveTask(b,t.id,'bad'),false);assert.equal(api.moveTask(b,'absent','todo'),false);
    assert.equal(api.deleteTask(b,'absent'),false);assert.equal(api.deleteTask(b,t.id),true);assert.equal(b.tasks.length,0);
  });
  await core('A3','Combined filters preserve insertion order and state',()=>{
    const b=api.createBoard();api.addTask(b,{title:'Alpha',priority:'high'});api.addTask(b,{title:'Alphabet',priority:'high',status:'doing'});api.addTask(b,{title:'Beta',priority:'low'});
    const before=clone(b);assert.equal(api.listTasks(b,{query:' ALP ',priority:'high',status:'doing'}).length,1);
    assert.deepEqual(ids(api.listTasks(b,{query:'',priority:'all',status:'all'})),ids(b.tasks));assert.equal(api.listTasks(b,{query:'none'}).length,0);assert.deepEqual(b,before);
  });
  await core('A4','Persistence validation and no future id collision',()=>{
    const b=api.createBoard();const a=api.addTask(b,{title:'A'});api.addTask(b,{title:'B'});api.deleteTask(b,a.id);const r=api.restore(api.serialize(b));assert.deepEqual(r.tasks,b.tasks);
    const next=api.addTask(r,{title:'C'});assert.notEqual(next.id,b.tasks[0].id);
    for(const raw of ['broken','null','{}',JSON.stringify({tasks:[{id:'1',title:' ',status:'todo',priority:'medium'}],nextId:2}),JSON.stringify({tasks:[...b.tasks,...b.tasks],nextId:3})])assert.equal(api.restore(raw).tasks.length,0);
  });
  if(stage===2) {
    await core('A9','One-level undo restores tasks and id counter',()=>{
      const b=api.createBoard(),before=clone(b);api.addTask(b,{title:'A'});assert.equal(api.undo(b),true);assert.deepEqual(b.tasks,before.tasks);assert.equal(b.nextId,before.nextId);assert.equal(api.undo(b),false);
      const t=api.addTask(b,{title:'B'});const snapshot=clone({tasks:b.tasks,nextId:b.nextId});api.moveTask(b,t.id,'done');api.addTask(b,{title:' '});assert.equal(api.undo(b),true);assert.deepEqual({tasks:b.tasks,nextId:b.nextId},snapshot);
      api.deleteTask(b,t.id);assert.equal(api.undo(b),true);assert.equal(b.tasks.length,1);
      api.editTask(b,t.id,{title:'Changed'});assert.equal(api.undo(b),true);assert.equal(b.tasks[0].title,'B');
    });
    await core('A10','Atomic import preserves state/undo on rejection',()=>{
      const b=api.createBoard();api.addTask(b,{title:'Existing'});const before=clone(b);
      assert.equal(api.importBoard(b,'invalid'),false);assert.deepEqual(b,before);
      const dup={tasks:[{id:'9',title:'A',status:'todo',priority:'high'},{id:'9',title:'B',status:'done',priority:'low'}],nextId:10};assert.equal(api.importBoard(b,JSON.stringify(dup)),false);assert.deepEqual(b,before);assert.equal(api.undo(b),true);
      assert.equal(api.importBoard(b,JSON.stringify({tasks:[dup.tasks[0]],nextId:10})),true);assert.equal(b.tasks[0].title,'A');assert.equal(api.undo(b),false);assert.notEqual(api.addTask(b,{title:'New'}).id,'9');
      assert.equal(api.importBoard(b,JSON.stringify({tasks:[],nextId:1})),true);assert.equal(b.tasks.length,0);
    });
    await core('A11','Serialized boards exclude undo state',()=>{
      const b=api.createBoard();api.addTask(b,{title:'A'});const raw=api.serialize(b),data=JSON.parse(raw);
      assert.ok(!Object.keys(data).some(k=>/undo|history|previous/i.test(k)));const restored=api.restore(raw);assert.equal(api.undo(restored),false);assert.equal(restored.tasks.length,1);
    });
  }
}

const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),relative=decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname);
  const file=path.resolve(workspace,'.'+relative);
  if(!file.startsWith(workspace+path.sep)){res.writeHead(403).end();return;}
  try{res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[path.extname(file)]||'text/plain');res.end(fs.readFileSync(file));}
  catch{res.writeHead(404).end('Not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
let browser;
try {
  browser=await chromium.launch({headless:true,channel:'chrome'});
  async function ui(id,name,fn,url='') {
    await test(id,name,async()=>{
      const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
      const errors=[];page.on('pageerror',e=>errors.push(String(e)));
      page.setDefaultTimeout(3000);
      try {await page.goto(base+'/'+url);await page.waitForTimeout(100);await fn(page);assert.deepEqual(errors,[],'Uncaught browser errors');}
      finally {await context.close();}
    });
  }
  await ui('UI1','Mobile layout and labelled usable controls',async p=>{
    assert.ok(await p.locator('h1').count());assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
    const controls=await p.locator('input:not([type=hidden]),select,textarea').evaluateAll(nodes=>nodes.map(n=>!!(n.labels?.length||n.getAttribute('aria-label')||n.getAttribute('aria-labelledby'))));
    assert.ok(controls.length>0);assert.ok(controls.every(Boolean),'Every form control needs an accessible name');
    await p.screenshot({path:path.join(path.dirname(output),'mobile-'+stage+'.png'),fullPage:true});
  });
  if(scenario==='website') {
    await ui('W4','UI catalogue filters and empty state',async p=>{
      assert.equal(await p.locator('[data-workshop-id]:visible').count(),6);await p.locator('#query').fill('Brno');assert.equal(await p.locator('[data-workshop-id]:visible').count(),2);assert.match(await p.locator('#result-count').innerText(),/2/);
      await p.locator('#query').fill('absent');assert.equal(await p.locator('[data-workshop-id]:visible').count(),0);assert.ok(await p.locator('#empty-state').isVisible());
    });
    await ui('W5','UI booking acknowledgement after valid input',async p=>{
      await p.locator('#booking-name').fill('Ana');await p.locator('#booking-email').fill('ana@example.com');await p.locator('#booking-workshop').selectOption('w1');await p.locator('#booking-submit').click();assert.match(await p.locator('#booking-status').innerText(),/book|confirm|reserv|success|thank/i);
    });
    if(stage===2) {
      await ui('W10','UI shortlist persists and survives filter reset',async p=>{
        await p.locator('[data-shortlist-id="w1"]').click();assert.match(await p.locator('#shortlist-count').innerText(),/1/);await p.reload();assert.match(await p.locator('#shortlist-count').innerText(),/1/);
        assert.deepEqual(await p.evaluate(()=>JSON.parse(localStorage.getItem('workshop-shortlist'))),['w1']);await p.locator('#query').fill('Brno');await p.locator('#reset-filters').click();assert.equal(await p.locator('#query').inputValue(),'');assert.equal(await p.locator('[data-workshop-id]:visible').count(),6);assert.match(await p.locator('#shortlist-count').innerText(),/1/);
      });
      await ui('W11','UI URL hydration and URL updates',async p=>{
        assert.equal(await p.locator('#query').inputValue(),'Brno');assert.equal(await p.locator('[data-workshop-id]:visible').count(),2);await p.locator('#query').fill('Prague');assert.equal(new URL(p.url()).searchParams.get('query'),'Prague');
        await p.locator('#reset-filters').click();assert.ok(!new URL(p.url()).searchParams.has('query'));
      },'?query=Brno&category=all&sort=title');
    }
  }
  if(scenario==='game') {
    await ui('G5','UI tile interaction updates completed-attempt count',async p=>{
      const tiles=p.locator('[data-card-id]');assert.equal(await tiles.count(),8);
      await tiles.nth(0).click();assert.match(await p.locator('#moves').innerText(),/\b0\b/);
      await tiles.nth(1).click();assert.match(await p.locator('#moves').innerText(),/\b1\b/);
      await p.waitForTimeout(950);assert.equal(await tiles.count(),8);
    });
    await ui('G6','UI restart clears moves and pending mismatch',async p=>{
      const tiles=p.locator('[data-card-id]');await tiles.nth(0).click();await tiles.nth(1).click();await p.locator('#restart').click();await p.waitForTimeout(950);assert.match(await p.locator('#moves').innerText(),/\b0\b/);assert.equal(await tiles.count(),8);
    });
    if(stage===2)await ui('G10','UI pause blocks input and restart resumes',async p=>{
      await p.locator('#pause').click();assert.match(await p.locator('#game-status').innerText(),/pause/i);const before=await p.locator('#moves').innerText();const tile=p.locator('[data-card-id]').first();if(await tile.isEnabled())await tile.click();assert.equal(await p.locator('#moves').innerText(),before);await p.locator('#restart').click();assert.ok(!/paused/i.test(await p.locator('#game-status').innerText()));assert.ok(await p.locator('#best-score').isVisible());
    });
  }
  if(scenario==='app') {
    await ui('A5','UI add, move and delete persist across reload',async p=>{
      await p.locator('#task-title').fill('Ship demo');await p.locator('#task-priority').selectOption('high');await p.locator('#add-task').click();const id=await p.locator('[data-task-id]').first().getAttribute('data-task-id');await p.locator('[data-move-id="'+id+'"]').selectOption('done');await p.reload();assert.equal(await p.locator('[data-column="done"] [data-task-id]').count(),1);await p.locator('[data-delete-id="'+id+'"]').click();await p.reload();assert.equal(await p.locator('[data-task-id]').count(),0);
    });
    await ui('A6','UI filters and unsafe input remain literal',async p=>{
      for(const [title,priority] of [['<img src=x onerror="window.injected=true">','high'],['Other','low']]){await p.locator('#task-title').fill(title);await p.locator('#task-priority').selectOption(priority);await p.locator('#add-task').click();}
      assert.equal(await p.evaluate(()=>window.injected),undefined);assert.equal(await p.locator('[data-task-id] img').count(),0);await p.locator('#priority-filter').selectOption('high');assert.equal(await p.locator('[data-task-id]:visible').count(),1);await p.locator('#task-query').fill('Other');assert.equal(await p.locator('[data-task-id]:visible').count(),0);
    });
    await ui('A7','UI tolerates corrupt stored board',async p=>{
      await p.evaluate(()=>localStorage.setItem('task-board','broken'));await p.reload();await p.locator('#task-title').fill('Recovery');await p.locator('#add-task').click();assert.equal(await p.locator('[data-task-id]').count(),1);
    });
    if(stage===2)await ui('A12','UI undo/import/export integration',async p=>{
      await p.locator('#task-title').fill('Keep');await p.locator('#add-task').click();await p.locator('#undo').click();assert.equal(await p.locator('[data-task-id]').count(),0);
      await p.locator('#import-json').fill(JSON.stringify({tasks:[{id:'9',title:'Imported',status:'doing',priority:'high'}],nextId:10}));await p.locator('#import-button').click();assert.equal(await p.locator('[data-column="doing"] [data-task-id]').count(),1);
      await p.locator('#import-json').fill('bad');await p.locator('#import-button').click();assert.match(await p.locator('#import-status').innerText(),/invalid|fail|error|could|unable/i);assert.equal(await p.locator('[data-task-id]').count(),1);await p.locator('#export-button').click();assert.equal(JSON.parse(await p.locator('#export-json').inputValue()).tasks[0].title,'Imported');await p.reload();assert.equal(await p.locator('[data-task-id]').count(),1);
    });
  }
} finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
const result={scenario,stage,passed:groups.filter(g=>g.passed).length,total:groups.length,groups};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({scenario,stage,passed:result.passed,total:result.total,failed:groups.filter(g=>!g.passed).map(g=>({id:g.id,error:g.error.split('\n')[0]}))}));
