import test from 'node:test';
import assert from 'node:assert/strict';
import {redactPayload,redactText} from '../src/privacy.js';
const sensitive='email: alice@example.com 身分證A123456789 電話0912-345-678 password="hunter22" Bearer abcdefg123';
test('shared text masks all requested categories without removing scam instructions',()=>{
 const clean=redactText(sensitive+' 請將驗證碼告知客服');
 for(const raw of ['alice@','A123456789','0912','hunter22','abcdefg123']) assert.ok(!clean.includes(raw));
 assert.ok(clean.includes('請將驗證碼告知客服'));
 assert.ok(!redactText('sk-proj-'+'x'.repeat(40)).includes('sk-proj-'));
});
test('transport mask preserves screenshot, URL and original local context',()=>{
 const original={context:{url:'https://example.com/path?token=original',text:sensitive,scripts:['api_key="secret-value"']},screenshot:'image-base64'};
 const masked=redactPayload(original);
 assert.equal(masked.screenshot,original.screenshot);
 assert.equal(masked.context.url,original.context.url);
 assert.ok(!masked.context.text.includes('alice@'));
 assert.ok(!masked.context.scripts[0].includes('secret-value'));
 assert.ok(original.context.text.includes('alice@'));
});
