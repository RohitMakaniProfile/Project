/* ══════════════════════════════════════════════════════════════
   NexusAPI — Frontend Application
   ══════════════════════════════════════════════════════════════ */

'use strict';

/* ── Globals ─────────────────────────────────────────────────── */
const BASE = '';   // same origin
const SESSION_JOBS = [];   // jobs created this session

/* ══════════════════════════════════════════════════════════════
   MAIN APP OBJECT
   ══════════════════════════════════════════════════════════════ */
const App = {
  token: null,
  user:  null,
  org:   null,

  /* ── Bootstrap ─────────────────────────────────────────────── */
  async init() {
    // 1. Check URL for token passed from OAuth callback redirect
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (urlToken) {
      this.token = urlToken;
      localStorage.setItem('nexusapi_token', urlToken);
      // Clean token from URL bar without reload
      window.history.replaceState({}, '', '/');
    } else {
      this.token = localStorage.getItem('nexusapi_token');
    }

    // 2. Show right view
    if (this.token) {
      try {
        await this.loadUser();
      } catch (_) {
        this.showLanding();
      }
    } else {
      this.showLanding();
    }

    // 3. Hide loading screen
    document.getElementById('loading-screen').style.display = 'none';
  },

  /* ── API helper ─────────────────────────────────────────────── */
  async api(method, path, body = null, extraHeaders = {}) {
    const headers = { 'Content-Type': 'application/json', ...extraHeaders };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

    const opts = { method, headers };
    if (body !== null) opts.body = JSON.stringify(body);

    const res = await fetch(BASE + path, opts);

    // Auto-logout on 401
    if (res.status === 401) {
      const data = await res.json().catch(() => ({}));
      this.logout();
      throw { status: 401, data };
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw { status: res.status, data };
    return { status: res.status, data };
  },

  /* ── Auth ───────────────────────────────────────────────────── */
  async loadUser() {
    const { data } = await this.api('GET', '/me');
    this.user = data.user;
    this.org  = data.organisation;
    this.showDashboard();
  },

  showLanding() {
    document.getElementById('landing-view').style.display = 'block';
    document.getElementById('dashboard-view').style.display = 'none';
    document.getElementById('nav-signin-btn').style.display = '';
    document.getElementById('nav-signout-btn').style.display = 'none';
    document.getElementById('nav-user-chip').style.display = 'none';
    this.startTerminalAnimation();
  },

  showDashboard() {
    document.getElementById('landing-view').style.display = 'none';
    document.getElementById('dashboard-view').style.display = '';
    document.getElementById('nav-signin-btn').style.display = 'none';
    document.getElementById('nav-signout-btn').style.display = '';
    document.getElementById('nav-user-chip').style.display = '';

    // Navbar user info
    const initials = this.user.name.split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase();
    document.getElementById('nav-avatar').textContent = initials;
    document.getElementById('nav-user-name-display').textContent = this.user.name;
    document.getElementById('nav-role-display').textContent = this.user.role;

    // Sidebar user info
    document.getElementById('dash-avatar').textContent = initials;
    document.getElementById('dash-user-name').textContent = this.user.name;
    document.getElementById('dash-user-email').textContent = this.user.email;
    document.getElementById('dash-user-role').textContent = this.user.role;
    document.getElementById('dash-org-name').textContent = this.org.name;
    document.getElementById('dash-org-slug').textContent = this.org.slug;

    // Hide grant form if non-admin
    if (this.user.role !== 'admin') {
      document.getElementById('grant-form').style.display = 'none';
      document.getElementById('grant-non-admin-notice').style.display = '';
    }

    this.loadBalance();
  },

  logout() {
    this.token = null;
    this.user  = null;
    this.org   = null;
    localStorage.removeItem('nexusapi_token');
    window.location.reload();
  },

  /* ── Balance & Transactions ─────────────────────────────────── */
  async loadBalance() {
    try {
      const { data } = await this.api('GET', '/credits/balance');
      const balance = data.balance;
      const txns    = data.recent_transactions || [];

      // Update all balance displays
      ['ov-balance','cr-balance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = balance.toLocaleString();
      });
      ['an-balance','su-balance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = balance.toLocaleString() + ' credits';
      });

      const orgEl = document.getElementById('ov-org-name');
      if (orgEl) orgEl.textContent = this.org ? this.org.name : '';
      const crOrg = document.getElementById('cr-org');
      if (crOrg) crOrg.textContent = this.org ? this.org.name : '';

      // Compute stats
      let granted = 0, spent = 0;
      txns.forEach(t => {
        if (t.amount > 0) granted += t.amount;
        else spent += Math.abs(t.amount);
      });
      setEl('ov-granted', '+' + granted.toLocaleString());
      setEl('ov-spent',   '-' + spent.toLocaleString());
      setEl('ov-txns',    txns.length + (txns.length === 10 ? '+' : ''));

      // Render transaction lists
      this.renderTxns('ov-txn-list', txns);
      this.renderTxns('cr-txn-list', txns);

    } catch (e) {
      // silently ignore — already logged out if 401
    }
  },

  renderTxns(containerId, txns) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!txns.length) {
      el.innerHTML = '<div class="empty-state">No transactions yet</div>';
      return;
    }
    el.innerHTML = txns.map(t => {
      const isCredit = t.amount > 0;
      const sign = isCredit ? '+' : '';
      const cls  = isCredit ? 'credit' : 'debit';
      const date = new Date(t.created_at).toLocaleString('en-GB', {
        day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'
      });
      return `
        <div class="txn-item">
          <span class="txn-amount ${cls}">${sign}${t.amount.toLocaleString()}</span>
          <span class="txn-reason">${escHtml(t.reason)}</span>
          <span class="txn-date">${date}</span>
        </div>`;
    }).join('');
  },

  /* ── Grant Credits ──────────────────────────────────────────── */
  async grantCredits() {
    const amount = parseInt(document.getElementById('grant-amount').value, 10);
    const reason = document.getElementById('grant-reason').value.trim();
    const resultEl = document.getElementById('grant-result');

    if (!amount || amount <= 0) { toast('Enter a valid amount', true); return; }
    if (!reason) { toast('Enter a reason', true); return; }

    setLoading('grant-btn', true, 'Granting…');
    resultEl.innerHTML = '';

    try {
      const { data } = await this.api('POST', '/credits/grant', { amount, reason });
      resultEl.className = 'result-box success';
      resultEl.textContent = `✓ Granted ${amount} credits. New balance: ${data.balance.toLocaleString()}`;
      document.getElementById('grant-amount').value = '';
      document.getElementById('grant-reason').value = '';
      toast(`Granted ${amount} credits successfully`);
      await this.loadBalance();
    } catch (e) {
      const msg = getErrMsg(e);
      resultEl.className = 'result-box error';
      resultEl.textContent = `✗ ${msg}`;
      toast(msg, true);
    } finally {
      setLoading('grant-btn', false, 'Grant Credits');
    }
  },

  /* ── Analyse ────────────────────────────────────────────────── */
  async runAnalyse() {
    const text = document.getElementById('an-text').value.trim();
    const idem = document.getElementById('an-idem').value.trim();

    if (text.length < 10) { toast('Text must be at least 10 characters', true); return; }
    if (text.length > 2000) { toast('Text must be at most 2000 characters', true); return; }

    setLoading('an-btn', true, 'Analysing…');
    document.getElementById('an-result-card').style.display = 'none';

    const headers = {};
    if (idem) headers['Idempotency-Key'] = idem;

    try {
      const { data } = await this.api('POST', '/api/analyse', { text }, headers);
      document.getElementById('an-result-card').style.display = '';
      document.getElementById('an-result-pre').textContent =
        JSON.stringify(data, null, 2);
      document.getElementById('an-result-meta').textContent =
        idem ? `Idempotency-Key: ${idem}` : 'Fresh request (no idempotency key)';
      toast('Analysis complete');
      await this.loadBalance();
    } catch (e) {
      const msg = getErrMsg(e);
      document.getElementById('an-result-card').style.display = '';
      document.getElementById('an-result-pre').textContent =
        JSON.stringify(e.data || { error: msg }, null, 2);
      document.getElementById('an-result-meta').textContent =
        `HTTP ${e.status || '?'}`;
      toast(msg, true);
    } finally {
      setLoading('an-btn', false, 'Run Analysis');
    }
  },

  /* ── Summarise ──────────────────────────────────────────────── */
  async runSummarise() {
    const text = document.getElementById('su-text').value.trim();
    const idem = document.getElementById('su-idem').value.trim();

    if (text.length < 10) { toast('Text must be at least 10 characters', true); return; }
    if (text.length > 2000) { toast('Text must be at most 2000 characters', true); return; }

    setLoading('su-btn', true, 'Submitting…');
    document.getElementById('su-result-card').style.display = 'none';

    const headers = {};
    if (idem) headers['Idempotency-Key'] = idem;

    try {
      const { data } = await this.api('POST', '/api/summarise', { text }, headers);
      const jobId = data.job_id;

      // Store in session
      SESSION_JOBS.unshift({ id: jobId, status: 'pending', created_at: new Date().toISOString() });
      this.renderSessionJobs();
      updateJobBadge();

      document.getElementById('su-result-card').style.display = '';
      document.getElementById('su-result-pre').textContent = JSON.stringify(data, null, 2);
      toast('Job submitted — ' + jobId.slice(0, 8) + '…');
      await this.loadBalance();

      // Auto-poll the job
      this.pollJob(jobId);
    } catch (e) {
      const msg = getErrMsg(e);
      document.getElementById('su-result-card').style.display = '';
      document.getElementById('su-result-pre').textContent =
        JSON.stringify(e.data || { error: msg }, null, 2);
      toast(msg, true);
    } finally {
      setLoading('su-btn', false, 'Submit Job');
    }
  },

  /* ── Job Polling ─────────────────────────────────────────────── */
  async pollJob(jobId, attempts = 0) {
    if (attempts > 20) return; // max ~40 seconds
    try {
      const { data } = await this.api('GET', `/api/jobs/${jobId}`);
      // Update in SESSION_JOBS
      const j = SESSION_JOBS.find(j => j.id === jobId);
      if (j) { j.status = data.status; j.result = data.result; j.error = data.error; }
      this.renderSessionJobs();
      updateJobBadge();

      if (data.status === 'pending' || data.status === 'running') {
        setTimeout(() => this.pollJob(jobId, attempts + 1), 2000);
      }
    } catch (_) {}
  },

  async lookupJob() {
    const jobId = document.getElementById('job-lookup-input').value.trim();
    if (!jobId) { toast('Enter a job ID', true); return; }

    const card = document.getElementById('job-lookup-card');
    const pre  = document.getElementById('job-lookup-pre');
    card.style.display = '';
    pre.textContent = 'Loading…';

    try {
      const { data } = await this.api('GET', `/api/jobs/${jobId}`);
      pre.textContent = JSON.stringify(data, null, 2);

      // Also update if in SESSION_JOBS
      const j = SESSION_JOBS.find(j => j.id === jobId);
      if (j) { j.status = data.status; j.result = data.result; this.renderSessionJobs(); }
    } catch (e) {
      pre.textContent = JSON.stringify(e.data || { error: getErrMsg(e) }, null, 2);
    }
  },

  async refreshAllJobs() {
    if (!SESSION_JOBS.length) { toast('No session jobs to refresh'); return; }
    for (const j of SESSION_JOBS) {
      if (j.status === 'pending' || j.status === 'running') {
        try {
          const { data } = await this.api('GET', `/api/jobs/${j.id}`);
          j.status = data.status; j.result = data.result; j.error = data.error;
        } catch (_) {}
      }
    }
    this.renderSessionJobs();
    updateJobBadge();
    toast('Jobs refreshed');
  },

  renderSessionJobs() {
    const el = document.getElementById('session-jobs-list');
    if (!el) return;
    if (!SESSION_JOBS.length) {
      el.innerHTML = '<div class="empty-state">No jobs created yet in this session</div>';
      return;
    }
    el.innerHTML = SESSION_JOBS.map(j => {
      const statusCls = `status-${j.status}`;
      const shortId = j.id.slice(0, 8) + '…';
      const resultSnippet = j.result
        ? `<div style="margin-top:8px;font-size:12px;color:var(--text-2)">${escHtml(j.result.slice(0,120))}${j.result.length > 120 ? '…' : ''}</div>`
        : (j.error ? `<div style="margin-top:8px;font-size:12px;color:var(--text-3)">Error: ${escHtml(j.error)}</div>` : '');
      return `
        <div class="job-item">
          <div>
            <div class="job-id">${j.id}</div>
            ${resultSnippet}
          </div>
          <span class="job-status-badge ${statusCls}">${j.status}</span>
        </div>`;
    }).join('');
  },

  /* ── Utilities ──────────────────────────────────────────────── */
  switchTab(tab, btn) {
    // Hide all tabs
    document.querySelectorAll('.dash-tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
    // Show selected
    document.getElementById('tab-' + tab).classList.add('active');
    if (btn) btn.classList.add('active');
    // Refresh balance on tab switch
    if (['overview','credits','analyse','summarise'].includes(tab)) {
      this.loadBalance();
    }
    if (tab === 'jobs') this.renderSessionJobs();
  },

  updateCharCount(textareaId, counterId) {
    const len = document.getElementById(textareaId).value.length;
    const el  = document.getElementById(counterId);
    el.textContent = `${len} / 2000`;
    el.className = 'char-count' + (len > 1800 ? ' warn' : '') + (len > 2000 ? ' over' : '');
  },

  fillIdemKey(inputId) {
    document.getElementById(inputId).value =
      'key-' + Math.random().toString(36).slice(2, 10) + '-' + Date.now();
  },

  /* ── Terminal Animation ─────────────────────────────────────── */
  startTerminalAnimation() {
    const sequences = [
      {
        cmd: "curl http://localhost:8000/health",
        out: { status: "healthy", database: "reachable", timestamp: new Date().toISOString() }
      },
      {
        cmd: 'curl -X POST /credits/grant \\\n     -H "Authorization: Bearer $TOKEN" \\\n     -d \'{"amount":100,"reason":"Monthly allocation"}\'',
        out: { message: "Granted 100 credits", balance: 100, transaction_id: "fe4a9ba0-531a" }
      },
      {
        cmd: 'curl -X POST /api/analyse \\\n     -H "Authorization: Bearer $TOKEN" \\\n     -d \'{"text":"The quick brown fox jumps over the lazy dog"}\'',
        out: { result: "Analysis complete. Word count: 9. Unique words: 8.", credits_remaining: 75 }
      },
      {
        cmd: 'curl -X POST /api/summarise \\\n     -H "Authorization: Bearer $TOKEN" \\\n     -d \'{"text":"FastAPI is a modern Python framework..."}\'',
        out: { job_id: "9d767976-470b-40f0-855e", credits_remaining: 65 }
      },
    ];

    let idx = 0;
    const cmdEl    = document.getElementById('t-cmd');
    const outEl    = document.getElementById('t-output');
    const cursorEl = document.getElementById('t-cursor');
    const nextEl   = document.getElementById('t-next');
    if (!cmdEl) return;

    const runSeq = () => {
      const seq = sequences[idx % sequences.length];
      idx++;

      // Reset
      cmdEl.textContent = '';
      outEl.textContent = '';
      outEl.classList.remove('visible');
      nextEl.style.display = 'none';
      cursorEl.style.display = 'inline-block';

      // Type the command
      let i = 0;
      const typeInterval = setInterval(() => {
        if (i >= seq.cmd.length) {
          clearInterval(typeInterval);
          // Show output after short delay
          setTimeout(() => {
            cursorEl.style.display = 'none';
            outEl.textContent = JSON.stringify(seq.out, null, 2);
            outEl.classList.add('visible');
            // Show next prompt
            setTimeout(() => {
              nextEl.style.display = 'flex';
              // Loop after pause
              setTimeout(runSeq, 2500);
            }, 600);
          }, 400);
          return;
        }
        cmdEl.textContent += seq.cmd[i];
        i++;
      }, 28);
    };

    setTimeout(runSeq, 800);
  }
};

/* ══════════════════════════════════════════════════════════════
   GLOBAL UI HELPERS
   ══════════════════════════════════════════════════════════════ */

/** Toggle API endpoint body open/closed */
function toggleEndpoint(headerEl) {
  const body = headerEl.nextElementSibling;
  body.classList.toggle('open');
}

/** Show/hide toast notification */
function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' toast-error' : '');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 3200);
}

/** Set element text content safely */
function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/** Escape HTML for safe insertion */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Extract error message from thrown API error */
function getErrMsg(e) {
  if (!e || !e.data) return 'An error occurred';
  const d = e.data;
  if (d.detail) {
    if (typeof d.detail === 'string') return d.detail;
    if (d.detail.message) return d.detail.message;
    if (d.detail.error) return d.detail.error;
  }
  if (d.message) return d.message;
  if (d.error)   return d.error;
  return `HTTP ${e.status}`;
}

/** Set button loading state */
function setLoading(btnId, isLoading, label) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = isLoading;
  if (isLoading) {
    btn.dataset.origHtml = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span>${label}`;
  } else {
    btn.innerHTML = btn.dataset.origHtml || label;
  }
}

/** Update jobs tab badge */
function updateJobBadge() {
  const running = SESSION_JOBS.filter(j => j.status === 'pending' || j.status === 'running').length;
  const badge = document.getElementById('job-count-badge');
  if (!badge) return;
  if (running > 0) {
    badge.style.display = 'inline-flex';
    badge.textContent = running;
    badge.style.cssText += `
      display:inline-flex;align-items:center;justify-content:center;
      width:16px;height:16px;border-radius:50%;
      background:var(--bg-5);font-size:10px;margin-left:auto;
      font-family:var(--mono);color:var(--text-2);`;
  } else {
    badge.style.display = 'none';
  }
}

/* ══════════════════════════════════════════════════════════════
   SMOOTH SCROLL FOR NAV LINKS
   ══════════════════════════════════════════════════════════════ */
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   NAVBAR SCROLL EFFECT
   ══════════════════════════════════════════════════════════════ */
window.addEventListener('scroll', () => {
  const nav = document.getElementById('navbar');
  if (nav) nav.style.borderBottomColor = window.scrollY > 20 ? 'var(--border-2)' : 'var(--border)';
}, { passive: true });

/* ══════════════════════════════════════════════════════════════
   BOOT
   ══════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => App.init());
