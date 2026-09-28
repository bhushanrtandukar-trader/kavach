"""Look and feel: page shell, CSS, and the service icon badges."""
import html as _html

# Brand colors — matched by substring of lowercase service name
SERVICE_COLORS = {
    'gmail': '#ea4335',        'google': '#4285f4',       'github': '#24292e',
    'facebook': '#1877f2',     'instagram': '#e4405f',    'twitter': '#1da1f2',
    'linkedin': '#0a66c2',     'microsoft': '#00a4ef',    'outlook': '#0078d4',
    'hotmail': '#0078d4',      'yahoo': '#6001d2',        'apple': '#555555',
    'icloud': '#3478f6',       'netflix': '#e50914',      'spotify': '#1db954',
    'youtube': '#ff0000',      'amazon': '#ff9900',       'aws': '#ff9900',
    'dropbox': '#0061ff',      'reddit': '#ff4500',       'discord': '#5865f2',
    'slack': '#4a154b',        'zoom': '#2d8cff',         'paypal': '#003087',
    'steam': '#1b2838',        'twitch': '#9146ff',       'tiktok': '#010101',
    'whatsapp': '#25d366',     'telegram': '#229ed9',     'signal': '#3a76f0',
    'notion': '#000000',       'figma': '#f24e1e',        'gitlab': '#fc6d26',
    'bitbucket': '#0052cc',    'digitalocean': '#0080ff', 'heroku': '#430098',
    'vercel': '#000000',       'netlify': '#00c7b7',      'cloudflare': '#f38020',
    'openai': '#10a37f',       'anthropic': '#d97757',
    # Nepal
    'esewa': '#4caf50',        'khalti': '#5e2bff',       'fonepay': '#ff6b00',
    'connectips': '#0066cc',   'nabil': '#c8102e',        'kumari': '#8b0000',
    'siddhartha': '#1a237e',   'prabhu': '#006400',       'laxmi': '#b8860b',
    'sunrise': '#ff8c00',      'global ime': '#003087',   'globalime': '#003087',
    'nepal bank': '#003087',   'nic asia': '#c8102e',     'nicasia': '#c8102e',
    'everest': '#1565c0',      'ntc': '#e30613',          'ncell': '#e30613',
    'namecheap': '#de3723',    'godaddy': '#1bdbdb',      'ime': '#00a651',
}

# Fallback palette — deterministic from service name hash
_PALETTE = [
    '#7F77DD','#378ADD','#1D9E75','#e06c75','#e5c07b',
    '#61afef','#98c379','#c678dd','#56b6c2','#d19a66',
]

def _service_color(service: str) -> str:
    s = service.lower().strip()
    match = next((col for key, col in SERVICE_COLORS.items() if key in s), None)
    if match:
        return match
    return _PALETTE[sum(ord(c) for c in s) % len(_PALETTE)]

def _service_abbrev(service: str, all_services: list) -> str:
    """
    Rules:
      Multi-word  -> initials of first two words, both UPPERCASE  (Nepal Bank -> NB)
      Single-word -> 1 letter (G) unless another single-word entry starts with
                     the same letter, then use first 2 chars (Gm / Gh / Go)
    """
    words = service.strip().split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()

    first = service.strip()[0].upper() if service.strip() else '?'
    # detect collision: other single-word services with same first letter
    clashes = [s for s in all_services
               if s.strip()
               and len(s.strip().split()) == 1
               and s.strip()[0].upper() == first
               and s.strip().lower() != service.strip().lower()]
    if not clashes:
        return first
    raw = service.strip()
    return (raw[0].upper() + raw[1].lower()) if len(raw) >= 2 else first

def get_icon_html(service: str, abbrev: str = None) -> str:
    """Colored letter badge. abbrev auto-computed if not provided."""
    if not service or not service.strip():
        service = '?'
    if abbrev is None:
        abbrev = service.strip()[0].upper()
    color     = _service_color(service)
    font_size = '11px' if len(abbrev) >= 2 else '13px'
    return (
        f'<span style="display:inline-flex;width:28px;height:28px;border-radius:7px;'
        f'background:{color};color:#fff;font-size:{font_size};font-weight:700;'
        f'align-items:center;justify-content:center;font-family:DM Sans,sans-serif;'
        f'box-shadow:0 2px 5px rgba(0,0,0,0.18);vertical-align:middle;'
        f'letter-spacing:0;flex-shrink:0;">{_html.escape(abbrev)}</span>'
    )

INDEX_STRING = '''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap" rel="stylesheet">
    <style>
        :root {
            --purple:#7F77DD; --purple-dark:#6a61cc; --purple-light:#f0effe;
            --blue:#378ADD;   --green:#1D9E75;        --green-dark:#178a65;
            --red:#e74c3c;    --bg:#f4f3fc;            --surface:#ffffff;
            --text-primary:#1a1830; --text-muted:#7a7a9d; --border:#e8e6f5;
            --shadow-sm:0 2px 8px rgba(127,119,221,0.08);
            --shadow-md:0 8px 30px rgba(127,119,221,0.13);
            --shadow-lg:0 20px 60px rgba(127,119,221,0.18);
            --radius:18px; --radius-sm:10px;
        }
        *,*::before,*::after{box-sizing:border-box;}
        body{font-family:"DM Sans",sans-serif;background:var(--bg);color:var(--text-primary);min-height:100vh;}
        h1,h2,h3,h4,h5,.navbar-brand{font-family:"Bricolage Grotesque",sans-serif!important;letter-spacing:-0.025em;}
        #login-screen .card{border:none;border-radius:var(--radius)!important;box-shadow:var(--shadow-lg)!important;background:var(--surface);overflow:hidden;}
        #login-screen .card::before{content:"";display:block;height:5px;background:linear-gradient(90deg,var(--purple),var(--blue));}
        .navbar{background:linear-gradient(110deg,var(--purple) 0%,var(--blue) 100%)!important;box-shadow:var(--shadow-md)!important;padding:14px 0!important;}
        .navbar-brand{font-size:1.1rem!important;font-weight:700!important;letter-spacing:-0.02em!important;color:#fff!important;}
        .card{border:1.5px solid var(--border)!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-sm)!important;}
        .btn{font-family:"DM Sans",sans-serif!important;font-weight:500!important;font-size:13.5px!important;letter-spacing:0.01em!important;border-radius:var(--radius-sm)!important;padding:8px 14px!important;transition:all 0.18s ease!important;}
        .btn-primary{background:var(--purple)!important;border-color:var(--purple)!important;box-shadow:0 4px 14px rgba(127,119,221,0.35)!important;}
        .btn-primary:hover{background:var(--purple-dark)!important;transform:translateY(-1px)!important;}
        .btn-success{background:var(--green)!important;border-color:var(--green)!important;color:#fff!important;}
        .btn-success:hover{background:var(--green-dark)!important;transform:translateY(-1px)!important;}
        .btn-danger{background:var(--red)!important;border-color:var(--red)!important;}
        .btn-danger:hover{transform:translateY(-1px)!important;}
        .btn-info{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important;}
        .btn-light{background:rgba(255,255,255,0.18)!important;border-color:rgba(255,255,255,0.55)!important;color:#fff!important;}
        .btn-light:hover{background:rgba(255,255,255,0.30)!important;}
        .btn-secondary{background:#ece9f8!important;border-color:#ece9f8!important;color:var(--purple)!important;}
        .btn-outline-secondary{color:var(--text-muted)!important;border-color:var(--border)!important;}
        .btn-outline-secondary:hover{background:var(--purple-light)!important;color:var(--purple)!important;border-color:var(--purple)!important;}
        .form-control,.form-select{font-family:"DM Sans",sans-serif!important;border:1.5px solid var(--border)!important;border-radius:var(--radius-sm)!important;padding:12px 16px!important;font-size:14px!important;transition:border-color 0.15s,box-shadow 0.15s!important;background:#faf9ff!important;}
        .form-control:focus{border-color:var(--purple)!important;box-shadow:0 0 0 3px rgba(127,119,221,0.15)!important;background:#fff!important;}
        textarea.form-control{padding:10px 14px!important;font-size:13px!important;}
        label,.form-label{font-family:"DM Sans",sans-serif!important;font-weight:500!important;font-size:12.5px!important;color:var(--text-muted)!important;text-transform:uppercase!important;letter-spacing:0.06em!important;margin-bottom:6px!important;}
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner th{font-family:"DM Sans",sans-serif!important;font-weight:600!important;font-size:11px!important;text-transform:uppercase!important;letter-spacing:0.08em!important;color:var(--text-muted)!important;background:var(--purple-light)!important;padding:11px 16px!important;border-bottom:2px solid var(--border)!important;}
        .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td{font-family:"DM Sans",sans-serif!important;font-size:13.5px!important;padding:11px 16px!important;border-bottom:1px solid var(--border)!important;color:var(--text-primary)!important;}
        .dash-table-container{border:1.5px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden!important;box-shadow:var(--shadow-sm)!important;}
        .modal-content{border:none!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-lg)!important;overflow:hidden!important;}
        .modal-header{font-family:"Bricolage Grotesque",sans-serif!important;background:var(--purple-light)!important;border-bottom:1.5px solid var(--border)!important;font-size:1.1rem!important;font-weight:700!important;padding:18px 24px!important;}
        .modal-body{padding:22px!important;}
        .modal-footer{border-top:1.5px solid var(--border)!important;padding:14px 24px!important;}
        .alert{border-radius:var(--radius-sm)!important;font-family:"DM Sans",sans-serif!important;font-weight:500!important;border:none!important;}
        .page-heading{font-family:"Bricolage Grotesque",sans-serif!important;font-size:1.15rem;font-weight:700;color:var(--text-primary);letter-spacing:-0.02em;}
        .input-group .btn{border-radius:0 var(--radius-sm) var(--radius-sm) 0!important;}
        #login-screen{background:radial-gradient(ellipse 80% 60% at 70% -10%,rgba(127,119,221,0.12) 0%,transparent 60%),radial-gradient(ellipse 60% 50% at 10% 90%,rgba(55,138,221,0.09) 0%,transparent 60%),var(--bg);}
        .copy-feedback-text{font-size:12px;color:var(--green);font-weight:500;}
        .btn-group .btn{border-radius:0!important;}
        .btn-group .btn:first-child{border-radius:var(--radius-sm) 0 0 var(--radius-sm)!important;}
        .btn-group .btn:last-child{border-radius:0 var(--radius-sm) var(--radius-sm) 0!important;}

        .role-badge{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:3px 9px;border-radius:20px;background:var(--purple-light);color:var(--purple);}
        .role-owner{background:#fff1d6;color:#a86400;} .role-admin{background:#ffe4e4;color:#b42318;}
        .role-auditor{background:#e0f2fe;color:#0369a1;} .role-manager{background:#fff1d6;color:#a86400;}
        .role-editor{background:#e6f6ee;color:#146c43;} .role-viewer{background:#eef0f4;color:#5b6172;}
        .pane-card{background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow-sm);}
        .nav-tabs .nav-link{font-family:"DM Sans",sans-serif;font-weight:500;color:var(--text-muted);border:none!important;border-bottom:2px solid transparent!important;}
        .nav-tabs .nav-link.active{color:var(--purple)!important;border-bottom:2px solid var(--purple)!important;background:transparent!important;}
        .nav-tabs{border-bottom:1.5px solid var(--border)!important;}
        .invite-code{font-family:monospace;font-size:15px;background:#faf9ff;border:1.5px dashed var(--purple);border-radius:10px;padding:12px 14px;word-break:break-all;user-select:all;}
        .link-btn{background:none;border:none;color:var(--purple);font-size:13px;padding:0;cursor:pointer;}
        .link-btn:hover{text-decoration:underline;}
    </style>
    <script>
        // Track last user interaction for auto-lock
        window._lastActivity = Date.now() / 1000;
        document.addEventListener("click",    function(){ window._lastActivity = Date.now()/1000; });
        document.addEventListener("keydown",  function(){ window._lastActivity = Date.now()/1000; });
        document.addEventListener("mousemove",function(){ window._lastActivity = Date.now()/1000; });
        document.addEventListener("scroll",   function(){ window._lastActivity = Date.now()/1000; }, true);
    </script>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''
