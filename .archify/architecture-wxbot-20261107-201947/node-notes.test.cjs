// Isolated headless browser: all file-system handles below are in-memory fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('C:/Users/fcc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  const results = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.addInitScript(() => {
    const missing = () => new DOMException('Fixture missing', 'NotFoundError');
    window.__notesFixture = {
      files: { 'wechat-client.md': '# 微信\n\n<img src=x onerror=alert(1)>', 'queue-worker.md': '# 队列工作器\n' },
      pickerCalls: 0, writes: 0, pickerError: '', wrongRoot: false, oldDiagramOnly: false,
      validatedDiagramPaths: []
    };
    const f = window.__notesFixture;
    const directory = {
      async getFileHandle(name, options = {}) {
        if (!(name in f.files)) {
          if (!options.create) throw missing();
          f.files[name] = '';
        }
        return {
          async getFile() { return new File([f.files[name]], name); },
          async createWritable(options) {
            if (options.mode !== 'exclusive') throw new Error('Expected exclusive writer');
            let pending;
            return {
              async write(text) { pending = text; },
              async close() { f.files[name] = pending; f.writes++; },
              async abort() {}
            };
          }
        };
      }
    };
    window.showDirectoryPicker = async () => {
      f.pickerCalls++;
      if (f.pickerError) throw new DOMException('Fixture picker failure', f.pickerError);
      return {
        async getFileHandle(name) {
          if (f.wrongRoot || !f.oldDiagramOnly || name !== 'ARCHITECTURE.html') throw missing();
          return {};
        },
        async getDirectoryHandle(name) {
          if (name === 'architecture-notes') return directory;
          if (name !== '.archify' || f.wrongRoot || f.oldDiagramOnly) throw missing();
          return {
            async getDirectoryHandle(child) {
              if (child !== 'architecture-wxbot-20261107-201947') throw missing();
              return {
                async getFileHandle(file) {
                  if (file !== 'wxbot.html') throw missing();
                  f.validatedDiagramPaths.push('.archify/' + child + '/' + file);
                  return {};
                }
              };
            }
          };
        }
      };
    };
  });
  const url = pathToFileURL(path.join(__dirname, 'wxbot.html')).href;
  await page.goto(url);
  await page.locator('svg [data-node-id="wechat"]').press('Enter');
  // A missing button is the intentional pre-implementation failure.
  assert.equal(await page.locator('#btn-node-note').count(), 1, 'node details must contain the Markdown button');
  await page.locator('#btn-node-note').click();
  await page.locator('#node-note[open]').waitFor();
  assert.equal(await page.locator('#note-path').textContent(), 'architecture-notes/wechat-client.md');

  for (const error of ['AbortError', 'NotAllowedError']) {
    await page.evaluate(error => { window.__notesFixture.pickerError = error; }, error);
    await page.locator('#note-connect').click();
    await page.waitForFunction(() => !document.querySelector('#note-connect').disabled);
    assert.equal(await page.locator('#note-edit').isVisible(), false);
  }
  await page.evaluate(() => { window.__notesFixture.pickerError = ''; window.__notesFixture.oldDiagramOnly = true; });
  await page.locator('#note-connect').click();
  await page.waitForFunction(() => !document.querySelector('#note-connect').disabled);
  assert.equal(await page.locator('#note-edit').isVisible(), false, 'a root with only the old diagram must be rejected');
  await page.evaluate(() => { window.__notesFixture.oldDiagramOnly = false; });
  await page.evaluate(() => { window.__notesFixture.pickerError = ''; window.__notesFixture.wrongRoot = true; });
  await page.locator('#note-connect').click();
  await page.waitForFunction(() => document.querySelector('#note-status').textContent.includes('请选择项目根目录'));
  await page.evaluate(() => { window.__notesFixture.wrongRoot = false; });
  await page.locator('#note-connect').click();
  await page.locator('#note-edit').waitFor();
  assert.match(await page.locator('#note-preview').textContent(), /<img src=x/);
  assert.equal(await page.locator('#note-preview img').count(), 0, 'Markdown is displayed as text');
  assert.deepEqual(await page.evaluate(() => window.__notesFixture.validatedDiagramPaths),
    ['.archify/architecture-wxbot-20261107-201947/wxbot.html']);
  results.push('picker cancellation/denial, old-only root rejection, new-only root acceptance, nested Archify HTML validation and safe preview');

  await page.locator('#note-edit').click();
  await page.locator('#note-editor').fill('# 微信\n\nUpdated fixture');
  await page.locator('#note-save').click();
  await page.waitForFunction(() => document.querySelector('#note-status').textContent === '已保存到文件。');
  assert.equal(await page.evaluate(() => window.__notesFixture.files['wechat-client.md']), '# 微信\n\nUpdated fixture');
  await page.locator('#note-close').click();
  assert.equal(await page.locator('#btn-node-note').evaluate(node => node === document.activeElement), true);
  assert.equal(await page.locator('#focus-chip').isVisible(), true, 'dialog interaction preserves the node passport');
  results.push('read, exclusive save and focus restoration without dismissing the passport');

  await page.locator('svg [data-node-id="worker"]').press('Enter');
  await page.locator('#btn-node-note').click();
  await page.locator('#note-edit').waitFor();
  assert.equal(await page.locator('#note-path').textContent(), 'architecture-notes/queue-worker.md');
  assert.equal(await page.locator('#note-preview').textContent(), '# 队列工作器\n');
  assert.equal(await page.evaluate(() => window.__notesFixture.pickerCalls), 5, 'reuse the granted root');
  await page.locator('#note-edit').click();
  await page.locator('#note-editor').fill('unsaved draft');
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator('#note-editor').press('Escape');
  assert.equal(await page.locator('#node-note').evaluate(node => node.open), true);
  assert.equal(await page.locator('#note-editor').inputValue(), 'unsaved draft');
  await page.evaluate(() => { window.__notesFixture.files['queue-worker.md'] = 'external modification'; });
  await page.locator('#note-save').click();
  await page.waitForFunction(() => document.querySelector('#note-status').textContent.includes('磁盘上的文件'));
  assert.equal(await page.evaluate(() => window.__notesFixture.files['queue-worker.md']), 'external modification');
  assert.equal(await page.locator('#note-editor').inputValue(), 'unsaved draft');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#note-close').click();
  results.push('node mapping, authorization reuse, draft protection and external-edit conflict');

  await page.locator('svg [data-node-id="backends"]').press('Enter');
  await page.locator('#btn-node-note').click();
  await page.locator('#note-edit').waitFor();
  assert.equal(await page.locator('#note-path').textContent(), 'architecture-notes/model-backends.md');
  assert.equal(await page.evaluate(() => 'model-backends.md' in window.__notesFixture.files), false);
  await page.locator('#note-edit').click();
  assert.equal(await page.locator('#note-editor').inputValue(), '# 可切换模型后端\n\n');
  await page.locator('#note-editor').fill('# New backend note');
  await page.locator('#note-save').click();
  await page.waitForFunction(() => window.__notesFixture.files['model-backends.md'] === '# New backend note');
  await page.locator('#note-close').click();
  results.push('new node files are created only by explicit save');

  // All nodes resolve deterministically; web and HTTP server share the original note.
  const expected = { wechat: 'wechat-client', wxui: 'wechat-ui', queue: 'queue-storage', worker: 'queue-worker',
    butler: 'butler', backends: 'model-backends', authority: 'identity-tools', business: 'business-storage',
    vault: 'knowledge-vault', web: 'dashboard', dashboard: 'dashboard', config: 'configuration' };
  for (const [id, note] of Object.entries(expected)) {
    await page.evaluate(id => Archify.focus.set(id, { toggle: false }), id);
    await page.locator('#btn-node-note').click();
    await page.locator('#note-edit').waitFor();
    assert.equal(await page.locator('#note-path').textContent(), `architecture-notes/${note}.md`);
    await page.locator('#note-close').click();
  }
  await page.evaluate(() => Archify.focus.setMany(['wechat', 'wxui'], { toggle: false }));
  await page.waitForFunction(() => document.querySelector('#btn-node-note').hidden);
  await page.evaluate(() => Archify.focus.inspectRelationshipById('receive'));
  await page.waitForFunction(() => document.querySelector('#btn-node-note').hidden);
  results.push('all 12 node mappings; hide the button for multi-node and relationship selections');

  await page.evaluate(() => Archify.focus.set('butler', { toggle: false }));
  await page.locator('#focus-chip').screenshot({ path: path.join(__dirname, 'node-document-button.png') });
  await page.locator('#btn-node-note').click();
  await page.locator('#note-edit').waitFor();
  assert.equal(await page.locator('#node-note').evaluate(node => {
    const box = node.getBoundingClientRect();
    return Math.abs(box.x + box.width / 2 - innerWidth / 2) < 2
      && Math.abs(box.y + box.height / 2 - innerHeight / 2) < 2;
  }), true, 'center the native dialog despite the generated viewer CSS reset');
  await page.emulateMedia({ colorScheme: 'light' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
  await page.screenshot({ path: path.join(__dirname, 'node-notes-light.png') });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: path.join(__dirname, 'node-notes-dark.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.locator('#node-note').evaluate(node => node.getBoundingClientRect().right <= innerWidth), true);
  await page.locator('#note-close').press('t');
  assert.equal(await page.evaluate(() => document.documentElement.getAttribute('data-theme')), 'dark');
  await page.locator('#note-close').click();
  results.push('light/dark captures, narrow viewport containment and modal keyboard isolation');

  const unsupported = await context.newPage();
  await unsupported.addInitScript(() => { window.showDirectoryPicker = undefined; });
  await unsupported.goto(url);
  await unsupported.locator('svg [data-node-id="wechat"]').press('Enter');
  await unsupported.locator('#btn-node-note').click();
  assert.match(await unsupported.locator('#note-status').textContent(), /Edge 或 Chrome/);
  assert.equal(await unsupported.locator('#note-connect').isVisible(), false);
  assert.deepEqual(errors, []);
  results.push('unsupported browser guidance; no page errors');
  fs.writeFileSync(path.join(__dirname, 'node-notes-verification.json'), JSON.stringify({
    status: 'pass', artifact: 'wxbot.html', sha256: require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(__dirname, 'wxbot.html'))).digest('hex'),
    browser: await browser.version(), checks: results, fixtures: 'in-memory directory/file handles only'
  }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'pass', checks: results }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
