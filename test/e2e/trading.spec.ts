import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────
// API Tests (no browser, fast)
// ─────────────────────────────────────────────
test.describe('API Tests', () => {
  test('health endpoint responds', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.status()).toBe(200);
    expect((await res.json()).status).toBe('ok');
  });

  test('watchlist: US tickers returned', async ({ request }) => {
    const res = await request.get('/api/watchlist?market=us');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
    expect(body.some((i: any) => i.ticker === 'AAPL')).toBe(true);
  });

  test('watchlist: India tickers returned', async ({ request }) => {
    const res = await request.get('/api/watchlist?market=in');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.some((i: any) => i.ticker === 'RELIANCE.NS')).toBe(true);
  });

  test('watchlist: US market has no Indian tickers', async ({ request }) => {
    const body = await (await request.get('/api/watchlist?market=us')).json();
    expect(body.every((i: any) => !i.ticker.endsWith('.NS') && !i.ticker.endsWith('.BO'))).toBe(true);
  });

  test('watchlist: India market has no US tickers', async ({ request }) => {
    const body = await (await request.get('/api/watchlist?market=in')).json();
    expect(body.every((i: any) => i.ticker.endsWith('.NS') || i.ticker.endsWith('.BO'))).toBe(true);
  });

  test('watchlist: add and remove ticker', async ({ request }) => {
    // Clean up first (idempotent)
    await request.delete('/api/watchlist/AMD?market=us');

    const addRes = await request.post('/api/watchlist', {
      data: { market: 'us', ticker: 'AMD' },
    });
    expect(addRes.status()).toBe(200);

    const list = await (await request.get('/api/watchlist?market=us')).json();
    expect(list.some((i: any) => i.ticker === 'AMD')).toBe(true);

    const delRes = await request.delete('/api/watchlist/AMD?market=us');
    expect(delRes.status()).toBe(200);

    const list2 = await (await request.get('/api/watchlist?market=us')).json();
    expect(list2.some((i: any) => i.ticker === 'AMD')).toBe(false);
  });

  test('watchlist: missing market parameter → 422', async ({ request }) => {
    const res = await request.get('/api/watchlist');
    expect([400, 422]).toContain(res.status());
  });

  test('portfolio: US portfolio shape', async ({ request }) => {
    const res = await request.get('/api/portfolio?market=us');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.market).toBe('us');
    expect(body.currency).toBe('USD');
    expect(typeof body.cash_balance).toBe('number');
    expect(body.cash_balance).toBeGreaterThan(0);
    expect(Array.isArray(body.positions)).toBe(true);
  });

  test('portfolio: India portfolio shape', async ({ request }) => {
    const res = await request.get('/api/portfolio?market=in');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.market).toBe('in');
    expect(body.currency).toBe('INR');
    expect(body.cash_balance).toBeGreaterThanOrEqual(90000);
  });

  test('portfolio: missing market → 422', async ({ request }) => {
    const res = await request.get('/api/portfolio');
    expect([400, 422]).toContain(res.status());
  });

  test('portfolio: invalid market → 400', async ({ request }) => {
    expect((await request.get('/api/portfolio?market=invalid')).status()).toBe(400);
  });

  test('trade: cross-market ticker rejected → 400', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'RELIANCE.NS', quantity: 1, side: 'buy' },
    });
    expect(res.status()).toBe(400);
  });

  test('trade: US ticker on India market rejected → 400', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { market: 'in', ticker: 'AAPL', quantity: 1, side: 'buy' },
    });
    expect(res.status()).toBe(400);
  });

  test('trade: buy US stock → cash decreases, position appears', async ({ request }) => {
    const initPortfolio = await (await request.get('/api/portfolio?market=us')).json();
    const initCash = initPortfolio.cash_balance;

    const tradeRes = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'MSFT', quantity: 2, side: 'buy' },
    });
    expect(tradeRes.status()).toBe(200);
    const tradeBody = await tradeRes.json();
    expect(tradeBody.trade.side).toBe('buy');
    expect(tradeBody.trade.quantity).toBe(2);

    const after = await (await request.get('/api/portfolio?market=us')).json();
    expect(after.cash_balance).toBeLessThan(initCash);
    expect(after.positions.some((p: any) => p.ticker === 'MSFT')).toBe(true);
  });

  test('trade: buy then sell → cash recovers', async ({ request }) => {
    const buyRes = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'NVDA', quantity: 2, side: 'buy' },
    });
    expect(buyRes.status()).toBe(200);
    const cashAfterBuy = (await (await request.get('/api/portfolio?market=us')).json()).cash_balance;

    const sellRes = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'NVDA', quantity: 1, side: 'sell' },
    });
    expect(sellRes.status()).toBe(200);

    const cashAfterSell = (await (await request.get('/api/portfolio?market=us')).json()).cash_balance;
    expect(cashAfterSell).toBeGreaterThan(cashAfterBuy);
  });

  test('trade: sell more than owned → 400', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'AAPL', quantity: 10000000, side: 'sell' },
    });
    expect(res.status()).toBe(400);
  });

  test('trade: buy with insufficient cash → 400', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { market: 'us', ticker: 'AAPL', quantity: 9999999, side: 'buy' },
    });
    expect(res.status()).toBe(400);
  });

  test('portfolio history: endpoint returns array', async ({ request }) => {
    const res = await request.get('/api/portfolio/history?market=us');
    expect(res.status()).toBe(200);
    expect(Array.isArray(await res.json())).toBe(true);
  });

  test('SSE stream: connects and receives price events', async ({ page }) => {
    // Use EventSource in the browser context — it handles streaming correctly
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const received = await page.evaluate(() => {
      return new Promise<boolean>((resolve) => {
        const es = new EventSource('/api/stream/prices');
        es.onmessage = (evt) => {
          try {
            const data = JSON.parse(evt.data);
            es.close();
            resolve(typeof data.ticker === 'string' && typeof data.price === 'number');
          } catch {
            es.close();
            resolve(false);
          }
        };
        es.onerror = () => { es.close(); resolve(false); };
        setTimeout(() => { es.close(); resolve(false); }, 8000);
      });
    });
    expect(received).toBe(true);
  });

  test('chat: mock buy message → assistant responds with trade', async ({ request }) => {
    const res = await request.post('/api/chat', {
      data: { market: 'us', message: 'please buy something for me' },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.role).toBe('assistant');
    expect(typeof body.content).toBe('string');
  });

  test('chat: mock neutral message → no trades executed', async ({ request }) => {
    const res = await request.post('/api/chat', {
      data: { market: 'us', message: 'how are you doing today' },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.content).toContain('Mock response');
    expect(body.actions).toBeNull();
  });

  test('chat history: messages stored and retrievable', async ({ request }) => {
    await request.post('/api/chat', { data: { market: 'us', message: 'test history message' } });
    const res = await request.get('/api/chat/history?market=us&limit=20');
    expect(res.status()).toBe(200);
    const history = await res.json();
    expect(history.length).toBeGreaterThan(0);
  });

  test('chat history: market scoped (US ≠ India)', async ({ request }) => {
    await request.post('/api/chat', { data: { market: 'us', message: 'hello from us' } });
    await request.post('/api/chat', { data: { market: 'in', message: 'hello from in' } });

    const usHistory = await (await request.get('/api/chat/history?market=us&limit=50')).json();
    expect(usHistory.every((m: any) => m.market === 'us')).toBe(true);

    const inHistory = await (await request.get('/api/chat/history?market=in&limit=50')).json();
    expect(inHistory.every((m: any) => m.market === 'in')).toBe(true);
  });
});

// ─────────────────────────────────────────────
// Browser / UI Tests
// ─────────────────────────────────────────────
test.describe('UI Tests', () => {
  test('page loads with FinAlly title', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveTitle(/FinAlly/i);
  });

  test('US and India market toggles are visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText('US').first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('India').first()).toBeVisible({ timeout: 8000 });
  });

  test('both wallet cards visible in header', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText(/US Portfolio/i).first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByText(/India Portfolio/i).first()).toBeVisible({ timeout: 8000 });
  });

  test('market toggle persists to localStorage', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const indiaBtn = page.getByRole('button', { name: /india/i }).first();
    await indiaBtn.waitFor({ state: 'visible', timeout: 8000 });
    await indiaBtn.click();
    const stored = await page.evaluate(() => localStorage.getItem('finally_market'));
    expect(stored).toBe('in');
  });
});
