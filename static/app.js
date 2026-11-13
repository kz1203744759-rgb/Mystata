const statusEl = document.querySelector('#status');
const configEl = document.querySelector('#config');
const button = document.querySelector('#run');
const keyInput = document.querySelector('#api-key');
const modelInput = document.querySelector('#model');
const settingsMessage = document.querySelector('#settings-message');

async function check() {
  try {
    const s = await (await fetch('/api/status', {cache: 'no-store'})).json();
    const missing = [];
    if (!s.stata_found) missing.push('Stata 路径');
    if (!s.uv_found) missing.push('uv');
    if (!s.api_key_set) missing.push('API 密钥');
    if (!s.model) missing.push('模型名称');
    statusEl.textContent = missing.length ? '需要配置' : '配置已就绪';
    statusEl.classList.toggle('warn', !!missing.length);
    configEl.textContent = missing.length ? '待配置：' + missing.join('、') + '。' : s.note;
    modelInput.value = s.model || '';
    keyInput.placeholder = s.api_key_set ? '已配置；留空可保留当前密钥' : '输入 API 密钥';
    document.querySelector('#key-hint').textContent = '密钥仅保存在本次运行的服务内，关闭服务后需要重新输入。';
  } catch (error) {
    statusEl.textContent = '无法连接本地服务';
    statusEl.classList.add('warn');
  }
}

document.querySelector('#settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const save = document.querySelector('#save-settings');
  save.disabled = true;
  settingsMessage.textContent = '正在保存…';
  try {
    const r = await fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({api_key:keyInput.value, model:modelInput.value})});
    const data = await r.json();
    if (!r.ok) throw Error(data.detail || '保存失败');
    keyInput.value = '';
    settingsMessage.textContent = '已保存到当前服务，立即生效。';
    await check();
  } catch (error) {
    settingsMessage.textContent = error.message;
  } finally { save.disabled = false; }
});

document.querySelector('#clear-settings').addEventListener('click', async () => {
  try {
    const r = await fetch('/api/settings', {method:'DELETE'});
    const data = await r.json();
    if (!r.ok) throw Error(data.detail || '清除失败');
    keyInput.value = '';
    settingsMessage.textContent = '已清除网页配置；如果系统环境变量已设置，仍会使用环境变量。';
    await check();
  } catch (error) { settingsMessage.textContent = error.message; }
});

button.addEventListener('click',async()=>{const message=document.querySelector('#prompt').value.trim();if(!message){document.querySelector('#prompt').focus();return}button.disabled=true;button.textContent='分析进行中…';document.querySelector('#result').hidden=false;document.querySelector('#events').textContent='正在运行，首次启动 MCP 可能需要几分钟。';document.querySelector('#answer').textContent='';document.querySelector('#path').textContent='';try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});const d=await r.json();if(!r.ok)throw Error(d.detail||'任务失败');document.querySelector('#events').textContent=d.events.length?'执行记录：'+d.events.map(x=>x.label+(x.error?'（报错）':'')).join(' → '):'本次未调用 Stata。';document.querySelector('#answer').textContent=d.answer;document.querySelector('#path').textContent='记录目录：'+d.run_dir}catch(e){document.querySelector('#events').textContent='任务未完成';document.querySelector('#answer').textContent=e.message}finally{button.disabled=false;button.innerHTML='开始分析 <b>↗</b>'}});check();
