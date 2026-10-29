const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const code = source.slice(source.indexOf('// A separate queue per card'), source.indexOf('async function previewTenderRepair'));
assert.ok(code.includes('function tenderChanged'), 'Use the real application queue implementation');
function setup(apiImpl) {
    const a = {id:'a', title:'Old', customer:'Original'}, b = {id:'b', title:'Other'};
    const feedback = {textContent:''}, timers = new Map(), calls=[], warnings=[];
    let next=0;
    const context = {state:{tenders:{current:a,items:[a,b],selected:'a'}}, document:{activeElement:{dataset:{tenderField:'customer'}}}, num:Number,
        $:()=>feedback, toast:(message)=>warnings.push(message), render:()=>{},
        setTimeout:fn=>{timers.set(++next,fn);return next;}, clearTimeout:id=>timers.delete(id),
        api:async(path,patch,method)=>{calls.push({path,patch,method});return apiImpl(path,patch,method);}};
    vm.createContext(context);
    vm.runInContext(code + '\nglobalThis.helpers={tenderChanged,flushTenderFields,discardTenderFieldEdits,tenderFieldSaves};',context);
    const edit = (field,value,type='text')=>context.helpers.tenderChanged({dataset:{tenderField:field},type,value,checked:value});
    return {context,helpers:context.helpers,a,b,edit,feedback,timers,calls,warnings};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function main(){
    let count=0;
    // Two independent fields in one debounce interval must produce one combined PATCH.
    {
        const env=setup(async(path,patch)=>({tender:{id:'a',...patch}}));
        env.edit('title','New');env.edit('customer','Buyer');
        assert.equal(env.timers.size,1);
        await [...env.timers.values()][0]();await tick();
        assert.equal(env.calls.length,1);
        assert.equal(env.calls[0].patch.title,'New');assert.equal(env.calls[0].patch.customer,'Buyer');
        assert.equal(env.feedback.textContent,'✓ Изменения сохранены'); count++;
    }
    // A delayed response from an old value must not replace a newly typed value.
    {
        let release;const pending=new Promise(resolve=>release=resolve);
        const env=setup(async(path,patch)=>{if(patch.title==='First')return pending;return {tender:{id:'a',...patch}};});
        env.edit('title','First');const flushing=env.helpers.flushTenderFields('a');
        env.edit('title','Second');env.edit('customer','Buyer');
        release({tender:{id:'a',title:'First',customer:'Original'}});await flushing;
        assert.equal(env.calls.length,2);assert.equal(env.calls[1].patch.title,'Second');
        assert.equal(env.calls[1].patch.customer,'Buyer');assert.equal(env.a.title,'Second');assert.equal(env.a.customer,'Buyer'); count++;
    }
    // An API error preserves both unsaved fields; explicit retry submits them together.
    {
        let fail=true;const env=setup(async(path,patch)=>{if(fail)throw Error('offline');return {tender:{id:'a',...patch}};});
        env.edit('title','Keep title');env.edit('customer','Keep customer');
        await assert.rejects(env.helpers.flushTenderFields('a'),/offline/);
        assert.equal(env.a.title,'Keep title');assert.equal(env.a.customer,'Keep customer');
        assert.match(env.feedback.textContent,/Ошибка сохранения/);fail=false;
        await env.helpers.flushTenderFields('a');assert.equal(env.calls[1].patch.title,'Keep title');assert.equal(env.calls[1].patch.customer,'Keep customer');count++;
    }
    // Each card has its own timer; saving the old card cannot switch the selected card.
    {
        const env=setup(async(path,patch)=>({tender:{id:path.split('/')[1],...patch}}));
        env.edit('title','A edit');env.context.state.tenders.current=env.b;env.context.state.tenders.selected='b';env.edit('title','B edit');
        assert.equal(env.timers.size,2);await Promise.all([env.helpers.flushTenderFields('a'),env.helpers.flushTenderFields('b')]);
        assert.equal(env.calls.length,2);assert.equal(env.a.title,'A edit');assert.equal(env.b.title,'B edit');assert.equal(env.context.state.tenders.current.id,'b');count++;
    }
    // Explicit flush is a barrier, including edits made while derived-data GET is in flight.
    {
        let releaseGet;const get=new Promise(resolve=>releaseGet=resolve);let firstGet=true;
        const env=setup(async(path,patch,method)=>{if(method==='GET'&&firstGet){firstGet=false;return get;}return {tender:{id:'a',...patch}};});
        env.edit('due_days',5,'number');const first=env.helpers.flushTenderFields('a');await tick();
        env.edit('customer','During refresh');const second=env.helpers.flushTenderFields('a');
        releaseGet({tender:{id:'a',due_days:5,customer:'Original'}});await second;await first;
        assert.equal(env.calls.filter(x=>x.method==='PATCH').length,2);assert.equal(env.a.customer,'During refresh');count++;
    }
    // Cancel a removed card's scheduled edits without another PATCH or stale feedback.
    {
        const env=setup(async(path,patch)=>({tender:{id:'a',...patch}}));env.edit('title','Removed');
        env.helpers.discardTenderFieldEdits('a');assert.equal(env.timers.size,0);await env.helpers.flushTenderFields('a');assert.equal(env.calls.length,0);count++;
    }
    console.log('Tender field batch regressions: '+count+' passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
