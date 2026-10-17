import test from 'node:test';
import assert from 'node:assert/strict';
import {nextSlide, previewWindow} from '../public/recommendations.js';

test('carousel advances one recommendation and wraps after the final complete viewport',()=>{
  let index=0;
  const positions=[];
  for(let step=0;step<5;step++)positions.push(index=nextSlide(index,8,5));
  assert.deepEqual(positions,[1,2,3,0,1]);
});

test('backwards navigation wraps to the final complete viewport',()=>{
  assert.equal(nextSlide(0,8,5,-1),3);
  assert.equal(nextSlide(3,8,5,-1),2);
  assert.equal(nextSlide(1,8,5,-1),0);
});

test('mobile visible count allows every card to enter the viewport',()=>{
  assert.equal(nextSlide(2,8,2),3);
  assert.equal(nextSlide(5,8,2),6);
  assert.equal(nextSlide(6,8,2),0);
  assert.equal(nextSlide(0,8,2,-1),6);
});

test('empty, single-card and fully visible shelves stay at the beginning',()=>{
  for(const [total,visible] of [[0,5],[1,1],[3,5],[5,5]]){
    assert.equal(nextSlide(0,total,visible),0);
    assert.equal(nextSlide(0,total,visible,-1),0);
  }
});

test('zero measured visibility still advances at least one card at a time',()=>{
  assert.equal(nextSlide(0,4,0),1);
  assert.equal(nextSlide(3,4,0),0);
});

test('short uploaded videos preview from the beginning without exceeding their duration',()=>{
  assert.deepEqual(previewWindow(.25),{start:0,end:.25});
  assert.deepEqual(previewWindow(8),{start:0,end:8});
  assert.deepEqual(previewWindow(12),{start:0,end:12});
  assert.deepEqual(previewWindow(30),{start:0,end:12});
});

test('long videos use a twelve-second excerpt with a sixty-second start cap',()=>{
  assert.deepEqual(previewWindow(120),{start:12,end:24});
  assert.deepEqual(previewWindow(600),{start:60,end:72});
  assert.deepEqual(previewWindow(7200),{start:60,end:72});
});

test('unavailable and invalid durations do not start previews',()=>{
  for(const duration of [NaN,Infinity,-Infinity,0,-1,undefined,null])assert.equal(previewWindow(duration),null);
});
