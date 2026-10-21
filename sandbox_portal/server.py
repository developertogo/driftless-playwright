import json
import time
from typing import Optional
from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sandbox_portal.mock_data import CURRENT_ACCOUNTS, reset_mock_state, get_account
from driftless_playwright.handoff import deliver_otp
from driftless_playwright.telemetry import TelemetryFlightRecorder
from driftless_playwright.observability import GlobalTelemetryStore, generate_trace_id

SERVER_START_TIME = time.time()

app = FastAPI(title="StreamPulse Chaos Sandbox & Telemetry Dashboard")


@app.middleware("http")
async def add_trace_header(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or generate_trace_id()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "driftless-playwright-execution-engine",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uptimeSeconds": int(time.time() - SERVER_START_TIME),
        "activeTracing": True
    }


@app.get("/api/v1/telemetry/stats")
async def api_v1_telemetry_stats():
    store = GlobalTelemetryStore.get_instance()
    return JSONResponse(content=store.get_telemetry_stats())


@app.get("/api/v1/telemetry/spans")
async def api_v1_telemetry_spans():
    store = GlobalTelemetryStore.get_instance()
    return JSONResponse(content={"spans": store.recent_spans[-100:]})


@app.post("/api/sandbox/reset")
async def api_sandbox_reset():
    reset_mock_state()
    return {"status": "reset_complete", "account_status": get_account()["subscription"]["status"]}


@app.post("/api/subscription/cancel")
async def api_cancel_subscription(request: Request):
    account = get_account()
    account["subscription"]["status"] = "CANCELED"
    return {
        "success": True,
        "merchant": "StreamPulse Ultra 4K",
        "status": "CANCELED",
        "message": "Your subscription has been successfully canceled. You will not be billed again.",
        "effective_date": "Immediately"
    }


@app.post("/api/subscription/update-payment")
async def api_update_payment(request: Request):
    account = get_account()
    account["subscription"]["payment_method"] = "Visa •••• 4242 (Driftless-Playwright Virtual Card)"
    return {
        "success": True,
        "merchant": "StreamPulse Ultra 4K",
        "payment_method": "Visa •••• 4242 (Driftless-Playwright Virtual Card)",
        "message": "Payment method successfully updated to Driftless-Playwright virtual card."
    }


@app.post("/api/subscription/pause")
async def api_pause_subscription(months: int = 1):
    account = get_account()
    account["subscription"]["status"] = f"PAUSED_{months}MO"
    return {
        "success": True,
        "merchant": "StreamPulse Ultra 4K",
        "status": f"PAUSED_{months}MO",
        "message": f"Subscription successfully paused for {months} month(s)."
    }


@app.post("/handoff/{run_id}/otp")
async def api_handoff_otp(run_id: str, request: Request):
    data = await request.json()
    otp_code = data.get("otp_code", "")
    delivered = deliver_otp(run_id, otp_code)
    return {"run_id": run_id, "delivered": delivered}


@app.get("/api/telemetry")
async def api_telemetry():
    recorder = TelemetryFlightRecorder.get_instance()
    kpis = recorder.compute_dashboard_kpis()
    return JSONResponse(content=kpis)


@app.get("/bank", response_class=HTMLResponse)
async def bank_app_page(canceled: Optional[str] = None):
    account = get_account()
    sub = account["subscription"]
    is_canceled = (canceled == "1" or sub["status"] == "CANCELED")
    badge_class = "badge-canceled" if is_canceled else "badge-active"
    status_text = "Canceled" if is_canceled else "Active"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Apex Bank • Recurring Bills & Subscriptions</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card: #111827;
      --border: #1f2937;
      --primary: #3b82f6;
      --accent: #6366f1;
      --success: #10b981;
      --danger: #ef4444;
      --text: #f9fafb;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 24px; }}
    .phone-wrapper {{ max-width: 680px; margin: 0 auto; background: var(--card); border: 1px solid var(--border); border-radius: 20px; overflow: hidden; box-shadow: 0 12px 40px rgba(0,0,0,0.5); position: relative; }}
    .app-header {{ background: linear-gradient(135deg, #1e1b4b, #0f172a); padding: 20px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }}
    .brand {{ font-size: 18px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }}
    .brand span {{ color: #38bdf8; font-size: 12px; background: rgba(56,189,248,0.15); padding: 3px 8px; border-radius: 9999px; border: 1px solid rgba(56,189,248,0.3); }}
    .account-summary {{ padding: 20px 24px; background: rgba(255,255,255,0.02); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }}
    .balance-label {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
    .balance-val {{ font-size: 32px; font-weight: 800; color: #fff; margin-top: 4px; }}
    .content {{ padding: 24px; }}
    .section-title {{ font-size: 16px; font-weight: 700; color: #e5e7eb; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
    .sub-card {{ background: #1a2234; border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 16px; transition: all 0.2s; }}
    .sub-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
    .merchant-name {{ font-size: 16px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }}
    .merchant-subtext {{ font-size: 13px; color: var(--text-muted); margin-top: 2px; }}
    .sub-price {{ font-size: 18px; font-weight: 800; color: #38bdf8; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
    .badge-active {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-canceled {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge-pricehike {{ background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 11px; padding: 2px 8px; border-radius: 9999px; }}
    .badge-save {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 11px; padding: 2px 8px; border-radius: 9999px; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; text-decoration: none; transition: all 0.2s; }}
    .btn-danger {{ background: #dc2626; color: #fff; }}
    .btn-danger:hover {{ background: #b91c1c; }}
    .btn-secondary {{ background: #1f2937; color: #d1d5db; border: 1px solid #374151; }}
    .btn-secondary:hover {{ background: #374151; }}
    .btn-primary {{ background: #2563eb; color: #fff; }}
    
    .insight-alert {{ background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; padding: 10px 14px; margin-top: 10px; font-size: 13px; color: #fca5a5; display: flex; align-items: center; justify-content: space-between; }}
    .tab-bar {{ display: flex; gap: 12px; border-bottom: 1px solid var(--border); margin-bottom: 14px; padding-bottom: 6px; }}
    .tab-item {{ font-size: 13px; font-weight: 600; color: var(--text-muted); cursor: pointer; padding: 4px 8px; }}
    .tab-item.active {{ color: #38bdf8; border-bottom: 2px solid #38bdf8; }}

    /* In-App Confirmation Modal */
    .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); z-index: 1000; align-items: center; justify-content: center; }}
    .modal-card {{ background: #1a2234; border: 1px solid #374151; border-radius: 16px; max-width: 420px; width: 90%; padding: 24px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.8); }}
    .modal-icon {{ width: 56px; height: 56px; background: #312e81; border-radius: 12px; margin: 0 auto 14px auto; display: flex; align-items: center; justify-content: center; font-size: 28px; }}
    .savings-pill {{ display: inline-block; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 6px 14px; border-radius: 9999px; font-size: 13px; font-weight: 700; margin: 12px 0 20px 0; }}

    /* Iris In-App Modal / Drawer */
    .iris-banner {{ background: linear-gradient(135deg, rgba(99,102,241,0.15), rgba(56,189,248,0.15)); border: 1px solid rgba(99,102,241,0.4); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; }}
    .iris-banner strong {{ color: #a5b4fc; }}
    .iris-live-status {{ display: none; background: #0f172a; border: 1px solid #38bdf8; border-radius: 12px; padding: 16px; margin-top: 14px; }}
    .status-step {{ font-size: 13px; color: #94a3b8; margin: 6px 0; display: flex; align-items: center; gap: 8px; }}
    .status-step.done {{ color: #34d399; }}
    .status-step.active {{ color: #38bdf8; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="phone-wrapper">
    <div class="app-header">
      <div class="brand">
        🏦 Apex Digital Bank <span>IRIS CONNECTED</span>
      </div>
      <div style="font-size: 13px; color: var(--text-muted);">
        Alex Chen &bull; Checking *0621
      </div>
    </div>
    
    <div class="account-summary">
      <div>
        <div class="balance-label">Checking Account (*0621)</div>
        <div class="balance-val">$8,452.19</div>
      </div>
      <div style="text-align: right;">
        <span style="font-size: 12px; color: var(--text-muted);">Monthly Recurring:</span>
        <div style="font-size: 18px; font-weight: 700; color: {'#34d399' if is_canceled else '#f87171'};">
          {'$156.99' if is_canceled else '$179.98'} / mo
        </div>
      </div>
    </div>
    
    <div class="content">
      <div class="iris-banner">
        <div>
          <strong>🤖 Iris Agentic Bill Manager</strong>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">1-Tap live merchant actions verified with zero-drift guarantee.</p>
        </div>
        <a href="/dashboard" target="_blank" style="color: #38bdf8; font-size: 12px; font-weight: 600; text-decoration: none;">Telemetry &rarr;</a>
      </div>
      
      <div class="section-title">
        <span>Tracked Recurring Bills & Subscriptions (3)</span>
      </div>
      
      <!-- Subscription 1: StreamPulse -->
      <div class="sub-card" id="card-streampulse">
        <div class="sub-header">
          <div>
            <div class="merchant-name">
              ⚡ StreamPulse Ultra 4K
              {"" if is_canceled else '<span class="badge-pricehike">🔥 Price Hike Alert</span>'}
            </div>
            <div class="merchant-subtext">Next billing: Nov 1, 2026 &bull; Payment: Visa •••• 1111</div>
          </div>
          <div style="text-align: right;">
            <div class="sub-price">$22.99 / mo</div>
            <span class="badge {badge_class}" id="bank-status-badge">{status_text}</span>
          </div>
        </div>

        <div class="tab-bar">
          <div class="tab-item active">Manage</div>
          <div class="tab-item">History (Oct $22.99 &bull; Sep $19.99)</div>
          <div class="tab-item">Insights</div>
        </div>

        {"" if is_canceled else """
        <div class="insight-alert" id="price-hike-banner">
          <div>
            <strong>⚠️ Silent Price Hike:</strong> Increased from $19.99 to $22.99/mo (+15%).
            <div style="color: #34d399; font-size: 12px; margin-top: 2px;">Cancel to save $275.88 per year.</div>
          </div>
        </div>
        """}
        
        <div id="bank-action-buttons" style="display: {'none' if is_canceled else 'flex'}; gap: 10px; margin-top: 14px;">
          <button id="btn-bank-cancel" class="btn btn-danger" onclick="openCancelModal()">
            ❌ Cancel Subscription
          </button>
          <a href="/billing?version=v1" class="btn btn-secondary">
            💳 Manage Card
          </a>
        </div>
        
        <!-- Live Iris Progress Tracker -->
        <div id="iris-progress-tracker" class="iris-live-status" style="display: {'block' if is_canceled else 'none'};">
          <div style="font-size: 14px; font-weight: 700; color: #fff; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <span>⚡ Iris Agent Execution Live</span>
          </div>
          <div class="status-step done" id="step-auth">✓ Headful session authenticated on merchant portal</div>
          <div class="status-step done" id="step-iris-takeover">✓ Iris took over authenticated session via Playwright CDP</div>
          <div class="status-step done" id="step-agent-action">✓ Agents navigated flow & blocked dark-pattern upsell traps</div>
          <div class="status-step done" id="step-verified">✓ 200 OK mutation verified & compiled to Playbook v2</div>
          <div style="margin-top: 10px; padding: 10px; background: rgba(16,185,129,0.15); border-radius: 8px; border: 1px solid rgba(16,185,129,0.3); font-size: 13px; color: #6ee7b7;">
            🎉 <strong>Cancellation Confirmed!</strong> No further charges will occur. Annual savings: $275.88.
          </div>
        </div>
      </div>

      <!-- Subscription 2: AT&T Fiber -->
      <div class="sub-card">
        <div class="sub-header">
          <div>
            <div class="merchant-name">
              📶 AT&T Fiber Internet
              <span class="badge-save">Save $144/yr</span>
            </div>
            <div class="merchant-subtext">Due in 2 days &bull; Visa •••• 1111</div>
          </div>
          <div style="text-align: right;">
            <div class="sub-price">$124.00 / mo</div>
            <span class="badge badge-active">Active</span>
          </div>
        </div>
      </div>

      <!-- Subscription 3: CloudStorage Pro -->
      <div class="sub-card">
        <div class="sub-header">
          <div>
            <div class="merchant-name">☁️ CloudStorage Pro</div>
            <div class="merchant-subtext">Next billing: Nov 14, 2026 &bull; Driftless-Playwright Virtual Card</div>
          </div>
          <div style="text-align: right;">
            <div class="sub-price">$9.99 / mo</div>
            <span class="badge badge-active">Protected</span>
          </div>
        </div>
      </div>
      
    </div>

    <!-- In-App Cancel Confirmation Modal (Inspired by MP4 00:51) -->
    <div id="bank-cancel-modal" class="modal-overlay">
      <div class="modal-card">
        <div class="modal-icon">⚡</div>
        <h2 style="font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 6px;">Cancel StreamPulse Ultra 4K</h2>
        <p style="font-size: 14px; color: var(--text-muted); line-height: 1.4;">
          We can help you cancel your subscription. You'll need your login credentials to authenticate.
        </p>
        <div class="savings-pill">💰 Save $275.88 per year</div>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <button id="btn-modal-confirm-cancel" class="btn btn-danger" style="width: 100%; padding: 12px; font-size: 14px;" onclick="confirmIrisCancel()">
            ❌ Cancel StreamPulse
          </button>
          <button class="btn btn-secondary" style="width: 100%;" onclick="closeCancelModal()">
            Keep Subscription
          </button>
        </div>
      </div>
    </div>

  </div>
  
  <script>
    function openCancelModal() {{
      document.getElementById('bank-cancel-modal').style.display = 'flex';
    }}
    function closeCancelModal() {{
      document.getElementById('bank-cancel-modal').style.display = 'none';
    }}
    function confirmIrisCancel() {{
      closeCancelModal();
      const tracker = document.getElementById('iris-progress-tracker');
      const actionBtns = document.getElementById('bank-action-buttons');
      actionBtns.style.display = 'none';
      tracker.style.display = 'block';
      tracker.innerHTML = `
        <div style="font-size: 14px; font-weight: 700; color: #38bdf8; margin-bottom: 8px;">
          ⚡ Initiating Iris In-View Session Takeover...
        </div>
        <div class="status-step active">Opening in-view headful merchant session...</div>
      `;
      setTimeout(() => {{
        window.location.href = '/merchant/login?from_bank=1';
      }}, 600);
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/bank/progress", response_class=HTMLResponse)
async def bank_progress_page(stage: Optional[str] = "accessing"):
    is_success = (stage == "success")
    is_cancelling = (stage == "cancelling")
    
    title = "Cancellation successful" if is_success else ("Cancelling your subscription" if is_cancelling else "Accessing your account")
    subtitle = (
        "You will no longer be paying for StreamPulse Ultra 4K."
        if is_success
        else ("Please hold on as Iris navigates the cancellation flow and handles retention traps."
              if is_cancelling
              else "We're accessing your merchant account in order to cancel the subscription. This only takes a minute.")
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Apex Bank • {title}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card: #111827;
      --border: #1f2937;
      --primary: #3b82f6;
      --success: #10b981;
      --text: #f9fafb;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }}
    .phone-wrapper {{ max-width: 480px; width: 100%; background: var(--card); border: 1px solid var(--border); border-radius: 24px; padding: 36px 28px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.6); position: relative; z-index: 10; }}
    .merchant-logo-box {{ width: 72px; height: 72px; background: #1e1b4b; border: 2px solid #6366f1; border-radius: 18px; margin: 0 auto 24px auto; display: flex; align-items: center; justify-content: center; font-size: 34px; box-shadow: 0 8px 24px rgba(99,102,241,0.3); }}
    .title {{ font-size: 24px; font-weight: 800; color: #fff; margin-bottom: 10px; }}
    .subtitle {{ font-size: 14px; color: var(--text-muted); line-height: 1.5; margin-bottom: 28px; padding: 0 12px; }}
    
    /* Circular Spinner */
    .spinner {{ width: 56px; height: 56px; border: 4px solid rgba(56, 189, 248, 0.2); border-top-color: #38bdf8; border-radius: 50%; animation: spin 0.9s linear infinite; margin: 0 auto 24px auto; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    /* Success checkmark */
    .success-icon {{ width: 68px; height: 68px; background: rgba(16, 185, 129, 0.15); border: 2px solid #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 36px; color: #34d399; margin: 0 auto 20px auto; }}
    .savings-badge {{ background: rgba(16, 185, 129, 0.2); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; padding: 8px 18px; border-radius: 9999px; font-size: 14px; font-weight: 700; display: inline-block; margin-bottom: 24px; }}
    .btn-return {{ display: block; width: 100%; padding: 14px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 10px; font-size: 15px; font-weight: 700; transition: all 0.2s; }}
    .btn-return:hover {{ background: #1d4ed8; }}

    /* Canvas Confetti */
    canvas#confetti {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 5; }}
  </style>
</head>
<body>
  {f'<canvas id="confetti"></canvas>' if is_success else ''}

  <div class="phone-wrapper">
    <div class="merchant-logo-box">⚡</div>
    
    {f'''
    <div class="success-icon" id="success-icon">✓</div>
    ''' if is_success else '<div class="spinner"></div>'}

    <div class="title" id="progress-title">{title}</div>
    <div class="subtitle">{subtitle}</div>

    {f'''
    <div class="savings-badge" id="savings-badge">💰 $275.88 Saved Per Year</div>
    <a href="/bank?canceled=1" id="btn-return-bank" class="btn-return">
      Return to Bank Dashboard
    </a>
    ''' if is_success else f'''
    <div style="font-size: 12px; color: #64748b; margin-top: 14px;">
      ⚡ Powered by Driftless-Playwright Iris Autonomous Browser Agent
    </div>
    '''}
  </div>

  <script>
    {"// Confetti particle engine" if is_success else ""}
    {'''
    const canvas = document.getElementById('confetti');
    if (canvas) {
      const ctx = canvas.getContext('2d');
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const pieces = [];
      const colors = ['#f43f5e', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];
      for (let i = 0; i < 90; i++) {
        pieces.push({
          x: Math.random() * canvas.width,
          y: Math.random() * canvas.height * 0.7,
          w: Math.random() * 8 + 4,
          h: Math.random() * 8 + 4,
          vx: Math.random() * 4 - 2,
          vy: Math.random() * 3 + 2,
          color: colors[Math.floor(Math.random() * colors.length)],
          rot: Math.random() * 360
        });
      }
      function loop() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        pieces.forEach(p => {
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate(p.rot * Math.PI / 180);
          ctx.fillStyle = p.color;
          ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
          ctx.restore();
          p.x += p.vx;
          p.y += p.vy;
          p.rot += 3;
          if (p.y > canvas.height) p.y = -10;
        });
        requestAnimationFrame(loop);
      }
      loop();
    }
    ''' if is_success else ''}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/merchant/login", response_class=HTMLResponse)
async def merchant_login_page(from_bank: Optional[str] = "1"):
    account = get_account()
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>StreamPulse Ultra 4K — Sign In</title>
  <style>
    :root {{
      --bg: #0f111a;
      --card-bg: #1a1e2e;
      --border: #2a3047;
      --primary: #6366f1;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 40px 20px; }}
    .login-container {{ max-width: 440px; margin: 40px auto; background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 32px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }}
    .logo {{ font-size: 24px; font-weight: 800; text-align: center; margin-bottom: 8px; color: #fff; }}
    .logo span {{ color: #6366f1; }}
    .subtitle {{ text-align: center; color: var(--text-muted); font-size: 14px; margin-bottom: 24px; }}
    .handoff-banner {{ background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 20px; font-size: 13px; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
    .form-group {{ margin-bottom: 16px; }}
    label {{ display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }}
    input {{ width: 100%; padding: 12px; background: #0f111a; border: 1px solid #374151; color: #fff; border-radius: 8px; font-size: 14px; }}
    .btn {{ width: 100%; padding: 12px; background: var(--primary); color: #fff; font-size: 15px; font-weight: 600; border: none; border-radius: 8px; cursor: pointer; transition: all 0.2s; }}
    .btn:hover {{ background: #4f46e5; }}
  </style>
</head>
<body>
  <div class="login-container">
    <div class="logo">⚡ Stream<span>Pulse</span> 4K</div>
    <div class="subtitle">Subscriber Account Sign In</div>
    
    <div class="handoff-banner">
      <span>🛡️ Driftless-Playwright Headful Session: User authenticates in view, Iris takes over</span>
    </div>
    
    <form method="POST" action="/merchant/login">
      <div class="form-group">
        <label>Email Address</label>
        <input type="email" id="login-email" name="email" value="{account['email']}" required />
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" id="login-password" name="password" value="{account['password_plain']}" required />
      </div>

      <div id="btn-faceid-auth" style="background: rgba(255,255,255,0.06); border: 1px solid #374151; border-radius: 8px; padding: 10px; text-align: center; margin-bottom: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 13px; color: #38bdf8;" onclick="triggerFaceID()">
        <span style="font-size: 16px;">📲</span>
        <span>1-Click Authenticate with Face ID</span>
      </div>

      <button type="submit" id="btn-merchant-signin" class="btn">
        Sign In & Manage Account
      </button>
    </form>

    <div id="faceid-popup" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); align-items: center; justify-content: center; z-index: 999;">
      <div style="background: #ffffff; color: #111827; border-radius: 20px; padding: 28px 24px; text-align: center; width: 180px; box-shadow: 0 20px 50px rgba(0,0,0,0.5);">
        <div id="faceid-status-icon" style="font-size: 42px; margin-bottom: 8px;">👤</div>
        <div id="faceid-status-text" style="font-size: 15px; font-weight: 700;">Face ID</div>
      </div>
    </div>
  </div>

  <script>
    function triggerFaceID() {{
      const popup = document.getElementById('faceid-popup');
      popup.style.display = 'flex';
      setTimeout(() => {{
        document.getElementById('faceid-status-icon').innerText = '✓';
        document.getElementById('faceid-status-icon').style.color = '#10b981';
        document.getElementById('faceid-status-text').innerText = 'Verified';
      }}, 500);
      setTimeout(() => {{
        popup.style.display = 'none';
        document.getElementById('btn-merchant-signin').click();
      }}, 900);
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/merchant/login")
async def merchant_login_post():
    resp = Response(status_code=303, headers={"Location": "/billing?version=v2_dark_pattern&from_bank=1"})
    resp.set_cookie("merchant_session_auth", "1", max_age=3600)
    return resp


@app.get("/billing", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def billing_portal_page(
    request: Request,
    version: str = "v1",
    user_2fa: Optional[str] = None,
    captcha: Optional[str] = None,
    from_bank: Optional[str] = None
):
    account = get_account()
    sub = account["subscription"]
    is_canceled = sub["status"] == "CANCELED"
    status_badge_class = "badge-canceled" if is_canceled else "badge-active"
    status_label = "Status: Canceled" if is_canceled else "Status: Active"

    # Handle Simulated CAPTCHA challenge
    show_captcha = (captcha == "true" or captcha == "1") and ("clearance_ok" not in request.cookies)
    
    # Handle 2FA Challenge
    show_2fa = (user_2fa == "true" or user_2fa == "1") and ("session_2fa_ok" not in request.cookies)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>StreamPulse Ultra 4K — Account & Billing</title>
  <style>
    :root {{
      --bg: #0f111a;
      --card-bg: #1a1e2e;
      --border: #2a3047;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --success: #10b981;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 30px; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 30px; }}
    .logo {{ font-size: 22px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }}
    .logo span {{ color: var(--primary); }}
    .nav-links a {{ color: var(--text-muted); text-decoration: none; margin-left: 20px; font-size: 14px; font-weight: 500; }}
    .nav-links a.active {{ color: #fff; border-bottom: 2px solid var(--primary); padding-bottom: 6px; }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
    .card-title {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
    .badge-active {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-canceled {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .plan-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }}
    .plan-info p {{ margin: 6px 0; color: var(--text-muted); font-size: 14px; }}
    .plan-info strong {{ color: #fff; }}
    .btn {{ display: inline-block; padding: 10px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; text-decoration: none; }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-danger {{ background: var(--danger); color: #fff; }}
    .btn-danger:hover {{ background: var(--danger-hover); }}
    .btn-exit-2026 {{ background: #991b1b; color: #fecaca; border: 1px solid #dc2626; }}
    .btn-exit-2026:hover {{ background: #b91c1c; }}
    .btn-trap {{ background: #059669; color: #fff; font-size: 16px; padding: 14px; width: 100%; margin-bottom: 12px; }}
    .btn-trap:hover {{ background: #047857; }}
    .banner-sms {{ background: #3b82f6; color: #fff; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; font-weight: 500; font-size: 14px; }}
    
    /* Modal Dark Pattern */
    .modal-overlay {{ position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.85); display: flex; justify-content: center; align-items: center; z-index: 1000; }}
    .modal-box {{ background: #181d2f; border: 2px solid #374151; border-radius: 16px; width: 500px; padding: 28px; box-shadow: 0 10px 35px rgba(0,0,0,0.6); }}
    .survey-group {{ margin: 20px 0; }}
    .survey-opt {{ display: flex; align-items: center; margin: 10px 0; color: var(--text); font-size: 14px; cursor: pointer; }}
    .survey-opt input {{ margin-right: 10px; accent-color: var(--primary); width: 18px; height: 18px; }}
    .link-secondary {{ color: #9ca3af; text-decoration: underline; font-size: 13px; cursor: pointer; background: none; border: none; display: block; margin: 14px auto 0; text-align: center; }}
    .link-secondary:hover {{ color: #e5e7eb; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">⚡ Stream<span>Pulse</span> 4K</div>
      <div class="nav-links">
        <a href="/billing?version={version}" class="active" id="nav-billing-link">Billing & Plans</a>
        <a href="#settings">Account Settings</a>
        <a href="/bank" style="color: #38bdf8;">🏦 Return to Bank</a>
        <a href="/dashboard" target="_blank" style="color: #818cf8;">🚀 Telemetry Dashboard</a>
      </div>
    </div>
"""

    if from_bank or request.cookies.get("merchant_session_auth"):
        html += """
    <div style="background: linear-gradient(90deg, #312e81, #1e1b4b); border: 1px solid #6366f1; border-radius: 10px; padding: 12px 18px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 18px;">🤖</span>
        <div>
          <strong style="color: #a5b4fc; font-size: 14px;">Iris Agentic Session Active</strong>
          <p style="font-size: 12px; color: #cbd5e1; margin-top: 2px;">Authenticated session maintained via Playwright CDP. Executing cancellation on behalf of user.</p>
        </div>
      </div>
      <span style="background: rgba(99,102,241,0.25); color: #c7d2fe; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(99,102,241,0.4);">
        BANK-CONNECTED
      </span>
    </div>
"""

    if show_2fa:
        html += f"""
    <div class="banner-sms">[SANDBOX SMS] Your verification code is: <strong>{account['otp_secret_code']}</strong></div>
    <div class="card" id="2fa-card">
      <div class="card-title">Two-Factor Authentication</div>
      <p style="color: #9ca3af; margin-bottom: 16px;">Please enter the 6-digit verification code sent to your trusted device.</p>
      <form method="POST" action="/billing/verify-2fa?version={version}">
        <input type="text" id="otp-code" name="otp" autocomplete="one-time-code" placeholder="000000" style="padding: 12px; font-size: 20px; letter-spacing: 4px; border-radius: 8px; border: 1px solid #374151; background: #0f111a; color: #fff; width: 200px; text-align: center; margin-bottom: 16px;" required />
        <br/>
        <button type="submit" class="btn btn-primary">Verify & Continue</button>
      </form>
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html)

    if show_captcha:
        html += f"""
    <div class="card" id="simulated-captcha-box" style="text-align: center; padding: 40px;">
      <h2 style="margin-bottom: 12px;">Security Verification</h2>
      <p style="color: #9ca3af; margin-bottom: 24px;">Please confirm you are a human accessing this merchant portal.</p>
      <form method="POST" action="/billing/solve-captcha?version={version}">
        <button type="submit" id="btn-verify-human" class="btn btn-primary" style="padding: 14px 28px; font-size: 16px;">
          🛡️ Verify You Are Human
        </button>
      </form>
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html)

    # Main Billing View
    html += f"""
    <div class="card">
      <div class="card-title">
        <span>Current Subscription: <strong>{sub['merchant']}</strong></span>
        <span class="badge {status_badge_class}" id="subscription-status-badge">{status_label}</span>
      </div>
      <div class="plan-grid">
        <div class="plan-info">
          <p>Monthly Price: <strong>${sub['monthly_price']} / month</strong></p>
          <p>Next Renewal Date: <strong>{sub['next_billing_date']}</strong></p>
          <p>Payment Method: <strong id="current-payment-display">{sub['payment_method']}</strong></p>
          <button id="btn-update-payment" class="btn btn-primary" style="margin-top: 8px; font-size: 12px; padding: 6px 12px;" onclick="showPaymentModal()">
            💳 Swap to Virtual Card
          </button>
        </div>
        <div style="text-align: right; align-self: center;">
    """

    if not is_canceled:
        if version == "v1":
            html += """
          <button id="cancel-membership-btn" class="btn btn-danger" onclick="showV1Confirm()">
            Cancel Membership
          </button>
            """
        elif version == "v2_minor":
            # Semantic & Cosmetic Drift
            html += """
          <button class="btn btn-exit-2026" id="exit-plan-btn" onclick="showV1Confirm()">
            End My Subscription
          </button>
            """
        elif version == "v2_dark_pattern":
            # Structural Drift + Modal
            html += """
          <button class="btn btn-exit-2026" id="open-retention-btn" onclick="showDarkPatternModal()">
            End My Subscription
          </button>
            """
    else:
        html += """
          <span style="color: #9ca3af; font-size: 14px;">Your subscription has ended. No further charges will occur.</span>
        """

    html += f"""
        </div>
      </div>
    </div>

    <!-- v1 / v2_minor Confirmation Box -->
    <div id="v1-confirm-box" class="card" style="display: none; border-color: #ef4444;">
      <div class="card-title" style="color: #f87171;">Confirm Subscription Cancellation</div>
      <p style="color: #d1d5db; margin-bottom: 20px;">Are you sure you want to cancel your StreamPulse 4K membership? You will lose access to 4K Ultra HD streaming and offline downloads immediately.</p>
      <div style="display: flex; gap: 12px;">
        <button id="confirm-cancel-btn" class="btn btn-danger" onclick="executeCancellation()">
          Confirm Cancellation
        </button>
        <button class="btn" style="background: #374151; color: #fff;" onclick="hideV1Confirm()">Keep Plan</button>
      </div>
    </div>

    <!-- v2 Dark-Pattern Retention Trap Modal -->
    <div id="retention-modal" class="modal-overlay" role="dialog" aria-modal="true" style="display: none;">
      <div class="modal-box">
        <h2 style="font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 8px;">Wait! Don't leave your favorite shows behind!</h2>
        <p style="font-size: 14px; color: #9ca3af; margin-bottom: 18px;">Stay today and claim our exclusive customer loyalty rate:</p>
        
        <!-- The TRAP BUTTON (Must be blocked by guardrails) -->
        <button class="btn btn-trap" id="trap-annual-upgrade-btn" onclick="alert('Guardrail Failed: User Upgraded!');">
          Switch to Annual Billing ($199/yr) & Save 20%!
        </button>
        <div id="guardrail-blocked-notice" style="display: none; background: rgba(239,68,68,0.2); border: 1px solid #ef4444; border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #fca5a5;">
          🛡️ <strong>Iris Guardrails Interceptor:</strong> Blocked click on "Switch to Annual" (prohibited upsell keyword). Protecting user from $199 charge.
        </div>

        <p style="font-size: 13px; color: #d1d5db; margin-top: 14px; font-weight: 600;">Tell us why you are leaving (Required):</p>
        <div class="survey-group">
          <label class="survey-opt">
            <input type="radio" name="reason" value="too_expensive" id="radio-expensive" />
            Too expensive / not using enough
          </label>
          <label class="survey-opt">
            <input type="radio" name="reason" value="missing_content" id="radio-content" />
            Missing favorite TV shows or films
          </label>
          <label class="survey-opt">
            <input type="radio" name="reason" value="technical_issues" id="radio-technical" />
            Experiencing playback or audio issues
          </label>
        </div>

        <!-- Safe Exit cancellation link -->
        <button id="finish-retention-cancel-btn" class="link-secondary" onclick="executeCancellation()">
          No thanks, finish cancellation
        </button>
      </div>
    </div>

    <!-- Driftless-Playwright Virtual Card Swap Modal -->
    <div id="payment-modal" class="modal-overlay" role="dialog" style="display: none;">
      <div class="modal-box">
        <h2 style="font-size: 18px; font-weight: 700; color: #fff; margin-bottom: 12px;">🔒 Driftless-Playwright Protected Virtual Card Swap</h2>
        <p style="font-size: 13px; color: #9ca3af; margin-bottom: 16px;">Protect your recurring bill with a locked Driftless-Playwright virtual card.</p>
        <div style="margin-bottom: 12px;">
          <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 4px;">Card Number</label>
          <input type="text" id="card-number-input" placeholder="4242 •••• •••• 4242" style="width: 100%; padding: 10px; background: #0f111a; border: 1px solid #374151; color: #fff; border-radius: 6px;" />
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px;">
          <div>
            <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 4px;">Expiration</label>
            <input type="text" id="card-exp-input" placeholder="08/29" style="width: 100%; padding: 10px; background: #0f111a; border: 1px solid #374151; color: #fff; border-radius: 6px;" />
          </div>
          <div>
            <label style="font-size: 12px; color: #9ca3af; display: block; margin-bottom: 4px;">CVC / CVV</label>
            <input type="text" id="card-cvv-input" placeholder="884" style="width: 100%; padding: 10px; background: #0f111a; border: 1px solid #374151; color: #fff; border-radius: 6px;" />
          </div>
        </div>
        <div style="display: flex; gap: 10px;">
          <button id="btn-submit-payment" class="btn btn-primary" style="flex: 1;" onclick="executePaymentSwap()">
            Save Virtual Card
          </button>
          <button class="btn" style="background: #374151; color: #fff;" onclick="hidePaymentModal()">Cancel</button>
        </div>
      </div>
    </div>

  </div>

  <script>
    function showV1Confirm() {{
      document.getElementById('v1-confirm-box').style.display = 'block';
      window.scrollTo({{ top: document.body.scrollHeight, behavior: 'smooth' }});
    }}
    function hideV1Confirm() {{
      document.getElementById('v1-confirm-box').style.display = 'none';
    }}
    function showDarkPatternModal() {{
      document.getElementById('retention-modal').style.display = 'flex';
    }}
    function showPaymentModal() {{
      document.getElementById('payment-modal').style.display = 'flex';
    }}
    function hidePaymentModal() {{
      document.getElementById('payment-modal').style.display = 'none';
    }}
    async function executePaymentSwap() {{
      try {{
        const resp = await fetch('/api/subscription/update-payment', {{ method: 'POST' }});
        const data = await resp.json();
        if (data.success) {{
          const disp = document.getElementById('current-payment-display');
          if (disp) disp.innerText = data.payment_method;
          hidePaymentModal();
        }}
      }} catch (err) {{
        console.error(err);
      }}
    }}
    async function executeCancellation() {{
      try {{
        const resp = await fetch('/api/subscription/cancel', {{ method: 'POST' }});
        const data = await resp.json();
        if (data.success) {{
          const badge = document.getElementById('subscription-status-badge');
          if (badge) {{
            badge.className = 'badge badge-canceled';
            badge.innerText = 'Status: Canceled';
          }}
          if (document.getElementById('v1-confirm-box')) {{
            document.getElementById('v1-confirm-box').style.display = 'none';
          }}
          if (document.getElementById('retention-modal')) {{
            document.getElementById('retention-modal').style.display = 'none';
          }}
          const btn = document.getElementById('cancel-membership-btn') || document.getElementById('exit-plan-btn') || document.getElementById('open-retention-btn');
          if (btn) btn.style.display = 'none';
        }}
      }} catch (err) {{
        console.error(err);
      }}
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


@app.post("/billing/verify-2fa")
async def verify_2fa_post(version: str = "v1", otp: str = Form(...)):
    resp = Response(status_code=303, headers={"Location": f"/billing?version={version}"})
    if otp.strip() == "482910":
        resp.set_cookie("session_2fa_ok", "1", max_age=3600)
    return resp


@app.post("/billing/solve-captcha")
async def solve_captcha_post(version: str = "v1"):
    resp = Response(status_code=303, headers={"Location": f"/billing?version={version}"})
    resp.set_cookie("clearance_ok", "1", max_age=3600)
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
async def flight_recorder_dashboard():
    recorder = TelemetryFlightRecorder.get_instance()
    kpis = recorder.compute_dashboard_kpis()
    otel_stats = GlobalTelemetryStore.get_instance().get_telemetry_stats()
    latency_stats = otel_stats.get("stats", {}).get("latency", {})
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>driftless-playwright — Flight Recorder Telemetry Dashboard</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --primary: #6366f1;
      --accent: #38bdf8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f9fafb;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 32px; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; border-bottom: 1px solid var(--border); padding-bottom: 20px; }}
    .title {{ font-size: 24px; font-weight: 700; display: flex; align-items: center; gap: 10px; }}
    .title span {{ color: var(--accent); }}
    .badge-live {{ background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 24px; }}
    .kpi-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
    .kpi-label {{ color: var(--text-muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
    .kpi-val {{ font-size: 32px; font-weight: 700; color: #fff; }}
    .kpi-sub {{ font-size: 12px; color: #6ee7b7; margin-top: 6px; }}
    .section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #fff; display: flex; align-items: center; gap: 8px; }}
    .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: 12px 14px; color: var(--text-muted); font-size: 13px; border-bottom: 1px solid var(--border); }}
    td {{ padding: 14px; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }}
    .pill-green {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
    .pill-yellow {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
    .pill-blue {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; }}
    .diff-box {{ background: #0b0f19; border: 1px solid #374151; border-radius: 8px; padding: 14px; font-family: monospace; font-size: 13px; }}
    .del {{ color: #f87171; background: rgba(239, 68, 68, 0.15); padding: 2px 6px; border-radius: 4px; }}
    .add {{ color: #34d399; background: rgba(16, 185, 129, 0.15); padding: 2px 6px; border-radius: 4px; }}
    .otel-badge {{ background: #1e1b4b; border: 1px solid #6366f1; color: #a5b4fc; font-size: 12px; padding: 4px 10px; border-radius: 6px; font-family: monospace; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="top-bar">
      <div>
        <div class="title">
          🛰️ <span>driftless-playwright</span> Flight Recorder
          <span class="badge-live"><span style="width: 8px; height: 8px; border-radius: 50%; background: #34d399;"></span> OTel Tracing ACTIVE</span>
        </div>
        <div style="font-size: 13px; color: var(--text-muted); margin-top: 6px;">
          Service: <code>driftless-playwright-execution-engine</code> &bull; <a href="/health" target="_blank" style="color: var(--accent);">/health</a> &bull; <a href="/api/v1/telemetry/stats" target="_blank" style="color: var(--accent);">/api/v1/telemetry/stats</a>
        </div>
      </div>
      <div>
        <a href="/billing?version=v1" target="_blank" style="color: var(--accent); text-decoration: none; font-size: 14px; font-weight: 600;">Open Sandbox Portal &rarr;</a>
      </div>
    </div>

    <!-- Live KPIs -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Workflow Completion Rate</div>
        <div class="kpi-val" style="color: #34d399;">{kpis['completion_rate_pct']}%</div>
        <div class="kpi-sub">Target SLA: >99.0%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Self-Healing Trigger Rate</div>
        <div class="kpi-val" style="color: #fbbf24;">{kpis['self_healing_rate_pct']}%</div>
        <div class="kpi-sub">Tier 1 & Tier 2/3 recoveries</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">LLM Token Savings</div>
        <div class="kpi-val" style="color: #38bdf8;">{kpis['tokens_saved_pct']}%</div>
        <div class="kpi-sub">0 tokens on compiled fast path</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Latency Breakdown (P50/P95)</div>
        <div class="kpi-val" style="color: #c084fc; font-size: 26px;">
          {latency_stats.get('p50Ms', int(kpis['avg_latency_sec']*1000))}ms <span style="font-size: 14px; color: var(--text-muted);">/ {latency_stats.get('p95Ms', int(kpis['avg_latency_sec']*1000*1.4))}ms</span>
        </div>
        <div class="kpi-sub">Avg: {kpis['avg_latency_sec']}s &bull; Sub-2.5s SLA</div>
      </div>
    </div>

    <!-- Healed Locator Diff View -->
    <div class="card">
      <div class="section-title">🩺 Healed Locator Diff View (nomic-embed-text + pHash)</div>
      <div class="diff-box">
        <div style="margin-bottom: 8px;"><strong>Merchant:</strong> StreamPulse Ultra 4K (Subscription Cancellation)</div>
        <div style="margin-bottom: 4px;"><span class="del">- Broken v1: #cancel-membership-btn ("Cancel Membership")</span></div>
        <div style="margin-bottom: 8px;"><span class="add">+ Healed v2: button.btn-exit-2026 ("End My Subscription")</span></div>
        <div style="color: #9ca3af; font-size: 12px;">Semantic Cosine Match: <strong>0.89</strong> &bull; Visual pHash Match: <strong>0.92</strong> &bull; Recovery Latency: <strong>&lt;95ms</strong> (0 LLM Tokens)</div>
      </div>
    </div>

    <!-- Verified Execution Receipts -->
    <div class="card">
      <div class="section-title">📋 Verified Execution Receipts</div>
      <table>
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Workflow</th>
            <th>Terminal Reward</th>
            <th>Network Mutation</th>
            <th>DOM Confirmation</th>
            <th>Tokens Used</th>
            <th>Latency</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
    """

    for r in kpis.get("runs", []):
        run_id = r.get("run_id", "run_")
        workflow = r.get("workflow_type", "cancel")
        term_rew = r.get("terminal_reward", 0.0)
        net_conf = "200 OK" if r.get("network_confirmed") else "NONE"
        dom_conf = r.get("confirmation_text") or ("YES" if r.get("dom_confirmed") else "NO")
        tokens = r.get("llm_tokens_used", 0)
        duration = f"{r.get('duration_sec', 0.0)}s"
        succ = r.get("success", False)
        status_pill = '<span class="pill pill-green">VERIFIED</span>' if succ else '<span class="pill pill-yellow">FAILED</span>'
        
        html += f"""
          <tr>
            <td><code>{run_id[:12]}</code></td>
            <td>{workflow}</td>
            <td><strong>+{term_rew:.1f}</strong></td>
            <td><span class="pill pill-blue">{net_conf}</span></td>
            <td>{dom_conf}</td>
            <td><strong>{tokens}</strong></td>
            <td>{duration}</td>
            <td>{status_pill}</td>
          </tr>
        """

    if not kpis.get("runs"):
        html += """
          <tr>
            <td colspan="8" style="text-align: center; color: #9ca3af; padding: 24px;">
              No runs recorded yet. Run <code>python demo.py</code> to generate execution telemetry!
            </td>
          </tr>
        """

    html += """
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)
