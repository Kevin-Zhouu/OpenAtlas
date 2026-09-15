import assert from 'node:assert/strict';
import {test} from 'node:test';
import {timeline,groupsAtScope,separatedLayout,meshTargets} from './scene-state.mjs';
const nodes={head:{name:'Head',children:[],members:[]}}, bounds={};
for(let s=0;s<8;s++){
 const id='system'+s;nodes.head.children.push(id);nodes[id]={name:id,children:[],members:[]};
 for(let i=0;i<90;i++){
  const key=`${id}-${i}`;nodes.head.members.push(key);nodes[id].members.push(key);nodes[id].children.push(key);nodes[key]={name:key,children:[],members:[key]};bounds[key]={min:[s,i*.01,0],max:[s+.3,i*.01+.2,.2]};
 }
}
test('root separates eight groups containing every eligible mesh, not eight leaves',()=>{
 const hidden=new Set(['system0-0']);const groups=groupsAtScope(nodes,'head',hidden);assert.equal(groups.length,8);assert.equal(groups.flatMap(g=>g.members).length,719);
 const layout=separatedLayout(groups,bounds);
 for(const t of [0,.01,.25,.5,.75,1,.5,0]){
  const targets=meshTargets(nodes.head.members,layout,t,hidden);assert.equal(targets.filter(m=>m.opacity>0).length,719);assert.equal(targets.find(m=>hidden.has(m.id)).opacity,0);
  if(t===0) assert(targets.every(m=>m.scale===1&&m.position.every(v=>v===0)));
 }
 const targets=meshTargets(nodes.head.members,layout,1);assert.deepEqual(targets[1].position,targets[2].position);assert.equal(targets[1].scale,targets[2].scale);
});
test('pagination happens at the current level and preserves normalized spacing',()=>{
 const groups=groupsAtScope(nodes,'system0');const layout=separatedLayout(groups,bounds,{page:1});assert.equal(layout.pages,12);assert.equal(layout.items[0].id,'system0-8');
 for(let i=0;i<layout.items.length;i++) for(let j=i+1;j<layout.items.length;j++){
  const center=g=>bounds[g.members[0]].min.map((v,k)=>(v+bounds[g.members[0]].max[k])/2*g.scale+g.translation[k]);
  const a=center(layout.items[i]),b=center(layout.items[j]);assert(Math.max(Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1]))>=2.24);
 }
});
test('scroll samples blend continuously in both directions',()=>{
 let previous=-1;for(let s=0;s<=200;s+=5){const x=timeline(s,[0,100,200]);const value=x.from+x.t;assert(value>=previous);assert(value-previous<=1);previous=value;}
 assert(timeline(50,[0,100]).t>.4);assert(timeline(50,[0,100]).t<.6);assert.throws(()=>timeline(0,[1,1]));
});
test('incomplete hierarchy is rejected instead of silently hiding anatomy',()=>{
 assert.throws(()=>groupsAtScope({...nodes,head:{...nodes.head,children:['system0']}},'head'));
});
