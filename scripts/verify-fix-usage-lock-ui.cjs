// Uses the same isolated Playwright browser acceptance as verify-m7-ui.cjs.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require('/Users/j/.npm/_npx/31e32ef8478fbf80/node_modules/playwright');
(async () => {
 const runtime=JSON.parse(fs.readFileSync('work/fix-usage-lock-ui-runtime.json','utf8'));
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'skill-pilot-fix-browser-'));
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,
  env:{...process.env,HOME:temporary,CFFIXED_USER_HOME:temporary,XDG_CONFIG_HOME:path.join(temporary,'.config'),XDG_CACHE_HOME:path.join(temporary,'.cache')}});
 const page=await browser.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const result={isolated_home:runtime.home,checks:[],browser_errors:errors};
 const check=(condition,label)=>{if(!condition) throw Error(label);result.checks.push(label);console.log(label);};
 const checkbox=(name,agent='Claude')=>page.getByRole('checkbox',{name:`${agent} 使用 ${name}`,exact:true});
 const waitChecked=(name,agent,value)=>page.waitForFunction(({name,agent,value})=>
  document.querySelector(`[aria-label="${agent} 使用 ${name}"]`)?.checked===value,{name,agent,value});
 try {
  let attempts=0;
  await page.route('**/api/usage',route=>attempts++===0 ? route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'正在统计用量，请稍候。',retry:true})}) : route.continue());
  await page.goto(runtime.url);
  await page.locator('#usage-progress').getByText('正在统计用量：已读 1 / 2 份记录',{exact:true}).waitFor();
  check(attempts>=2,'用量库暂时忙时自动重试，用户无需手动刷新');
  check(true,'顶部显示逐文件进度 1 / 2，扫描持有写锁');
  await page.getByRole('button',{name:'勾选表',exact:true}).click();
  await checkbox('grill-me').waitFor();
  check((await page.locator('#assignment-rows').innerText()).includes('正在统计（第一次需要几分钟）'),'用量未完成时显示正在统计');
  await page.getByRole('searchbox',{name:'搜索分配技能'}).fill('grill-me');
  await checkbox('grill-me').check();
  await waitChecked('grilling','Claude',true);
  check(await checkbox('grill-me').isChecked(),'持锁期间 grill-me 勾选预览成功');
  check(await checkbox('grilling').locator('..').getByText('因为 grill-me 需要它',{exact:true}).isVisible(),'grilling 自动勾上，格子旁显示原因');
  check(await page.locator('#assignment-apply').isEnabled(),'统计期间仍可应用分配');
  await page.getByRole('button',{name:'清理',exact:true}).click();
  await page.locator('#cleanup-status').getByText('正在统计，完成后再生成名单。',{exact:true}).waitFor();
  check(await page.locator('[data-cleanup]').count()===0 && await page.locator('#cleanup-apply').isDisabled(),'统计未完成不生成清理名单');
  await page.getByRole('button',{name:'勾选表',exact:true}).click();
  fs.writeFileSync(runtime.release,'release');
  await page.locator('#usage-progress').waitFor({state:'hidden'});
  await page.locator('#assignment-rows').getByText('Codex 最近使用：2026-10-10',{exact:true}).first().waitFor();
  check(true,'释放写锁后顶部进度自动消失，最近使用自动显示真实日期');
  check(await checkbox('grill-me').isChecked() && await checkbox('grilling').isChecked(),'用量自动刷新保留未应用的依赖分配');
  const revision=()=>JSON.parse(fs.readFileSync(runtime.home+'/.skill-pilot/registry.json','utf8'));
  check(!revision().skills['grill-me'].assigned_agents.includes('claude'),'预览尚未改动实际分配');
  await page.locator('#assignment-search').fill('');
  const summary=await page.locator('#pending-summary').innerText();
  await page.route('**/api/assignment/preview',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'暂时没能核对，请再试一次。'})}));
  await checkbox('other').click();
  await waitChecked('other','Claude',false);
  check(await checkbox('other').locator('..').getByText('这次勾选没改成：暂时没能核对，请再试一次。',{exact:true}).isVisible(),'预览失败时复原勾选，同行显示原因');
  check(await page.locator('#pending-summary').innerText()===summary && await checkbox('grilling').isChecked(),'失败回滚保留此前成功的待应用改动');
  await checkbox('grill-me','Codex').click();
  await waitChecked('grill-me','Codex',true);
  check(await checkbox('grill-me','Codex').locator('..').getByText(/这次勾选没改成/).isVisible(),'取消勾选失败时同样恢复原状');
  await page.unroute('**/api/assignment/preview');
  await checkbox('other').check();
  await page.locator('#pending-summary').getByText('将给 Claude 加 3 个',{exact:true}).waitFor();
  check(await checkbox('other').isChecked(),'接口恢复后可以再次勾选');
  check(!errors.length,'浏览器无 JavaScript 异常');
  result.status='passed';
 } catch(e) {result.status='failed';result.error=e.message;throw e;}
 finally {
  fs.writeFileSync(runtime.release,'release');
  await page.close();await browser.close();fs.rmSync(temporary,{recursive:true,force:true});
  fs.writeFileSync('work/fix-usage-lock-ui-acceptance.json',JSON.stringify(result,null,2)+'\n');
 }
 console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
