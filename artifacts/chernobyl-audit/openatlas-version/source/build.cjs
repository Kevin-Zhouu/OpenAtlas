const fs=require('fs'),path=require('path');
const root=__dirname;
let html=fs.readFileSync(path.join(root,'index.html'),'utf8');
let three=fs.readFileSync(path.join(root,'vendor/three.cjs'),'utf8');
three='var THREE = (() => { const exports = {};\n'+three+'\nreturn exports; })();';
let orbit=fs.readFileSync(path.join(root,'vendor/OrbitControls.js'),'utf8');
orbit=orbit.replace(/import\s*\{([\s\S]*?)\}\s*from 'three';/,(_,names)=>'const {'+names+'} = THREE;').replace(/export\s*\{\s*OrbitControls\s*\};?/,'');
for(const [tag,body] of [['STYLE',fs.readFileSync(path.join(root,'style.css'),'utf8')],['THREE',three],['ORBIT',orbit],['APP',fs.readFileSync(path.join(root,'app.js'),'utf8')]]) html=html.replace('/*'+tag+'*/',()=>body.replace(/<\/script/gi,'<\\/script'));
const dist=path.resolve(root,'../dist');fs.mkdirSync(dist,{recursive:true});fs.writeFileSync(path.join(dist,'index.html'),html);console.log('Built dist/index.html ('+html.length+' bytes)');
