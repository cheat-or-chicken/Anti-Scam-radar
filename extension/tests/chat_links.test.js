import test from 'node:test';
import assert from 'node:assert/strict';
import {extractLinks} from '../../ChatRoom/link_checks.mjs';
test('chat URL extraction handles punctuation, duplicates, bare domains and excludes emails',()=>{
 assert.deepEqual(extractLinks('請看 https://example.com/a。另看（www.example.org），ftec-08.twietio.vip https://example.com/a'),['https://example.com/a','https://www.example.org/','https://ftec-08.twietio.vip/']);
 assert.deepEqual(extractLinks('alice@example.com javascript:alert(1) https://user:pass@example.com'),[]);
});
