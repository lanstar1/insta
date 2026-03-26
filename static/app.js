/* ─── LANstar Insta Agent - Frontend ─── */

const API = '';
let currentPage = 'dashboard';
let state = {
  videos: { data: [], page: 1, total: 0, topic: 'all', search: '', sort: 'views_desc' },
  plans: { data: [], page: 1, total: 0 },
  topics: [],
  stats: {}
};

// ─── Navigation ───
function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.querySelector(`[data-page="${page}"]`).classList.add('active');

  const titles = { dashboard: '대시보드', ideas: '아이디어 뱅크', plans: '콘텐츠 기획', script: '스크립트 에디터', media: '미디어 생성', publish: '업로드/스케줄', templates: '템포 규칙' };
  document.getElementById('pageTitle').textContent = titles[page] || '';

  if (page === 'dashboard') loadDashboard();
  else if (page === 'ideas') loadIdeas();
  else if (page === 'plans') loadPlans();
  else if (page === 'script') loadScriptEditor();
  else if (page === 'media') loadMediaPage();
  else if (page === 'publish') loadPublishPage();
  else if (page === 'templates') loadTemplates();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ─── API Helper ───
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── Dashboard ───
async function loadDashboard() {
  const [stats, topics] = await Promise.all([
    api('/api/stats'),
    api('/api/topics')
  ]);
  state.stats = stats;
  state.topics = topics;

  document.getElementById('videoCount').textContent = `영상 ${stats.total_videos}개`;

  const el = document.getElementById('page-dashboard');
  const planTotal = stats.total_plans || 0;
  const planStatus = stats.plan_status || {};
  const planTypes = stats.plan_types || {};

  el.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="sc-label">YouTube 원본 영상</div>
        <div class="sc-value" style="color:var(--cyan)">${stats.total_videos}</div>
        <div class="sc-sub">${topics.length}개 주제</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">콘텐츠 기획</div>
        <div class="sc-value" style="color:var(--yellow)">${planTotal}</div>
        <div class="sc-sub">생성됨</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">릴스 기획</div>
        <div class="sc-value" style="color:var(--accent)">${planTypes.reels || 0}</div>
        <div class="sc-sub">키네틱/BA/POV</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">카드뉴스 / 스토리</div>
        <div class="sc-value" style="color:var(--orange)">${(planTypes.card_news || 0) + (planTypes.story || 0)}</div>
        <div class="sc-sub">기획됨</div>
      </div>
    </div>

    <div class="section-title">📊 주제별 영상 분포</div>
    <div class="video-grid" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr));">
      ${topics.map(t => `
        <div class="video-card" onclick="navigate('ideas');filterByTopic('${t.topic}')" style="cursor:pointer;">
          <div class="vc-body">
            <div class="vc-title">${t.topic}</div>
            <div class="vc-meta" style="margin-top:6px;">
              <span style="font-family:'Black Han Sans';font-size:1.3em;color:var(--cyan);">${t.count}</span>
              <span style="font-size:0.78em;color:var(--text-dim);">개 영상</span>
            </div>
            <div style="font-size:0.78em;color:var(--text-dim);margin-top:4px;">
              평균 ${formatViews(t.avg_views)}회 · 총 ${formatViews(t.total_views)}회
            </div>
          </div>
        </div>
      `).join('')}
    </div>

    <div class="section-title" style="margin-top:24px;">🎯 릴스 스타일 전략</div>
    <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);">
      <div class="stat-card" style="border-color:rgba(255,45,85,0.3);">
        <div class="sc-label">키네틱 타이포</div>
        <div class="sc-value" style="color:var(--accent);">60%</div>
        <div class="sc-sub">주력 · 빠른 텍스트 전환 · 음소거 대응</div>
      </div>
      <div class="stat-card" style="border-color:rgba(255,214,10,0.3);">
        <div class="sc-label">Before/After</div>
        <div class="sc-value" style="color:var(--yellow);">20%</div>
        <div class="sc-sub">비교형 · 분할 화면 · 저장률 최고</div>
      </div>
      <div class="stat-card" style="border-color:rgba(0,230,118,0.3);">
        <div class="sc-label">POV 상황극</div>
        <div class="sc-value" style="color:var(--green);">20%</div>
        <div class="sc-sub">카톡 대화 · 공감/유머 · DM 공유</div>
      </div>
    </div>

    <div class="section-title" style="margin-top:24px;">⚡ 템포 규칙 요약</div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="sc-label">후킹 (Hook)</div>
        <div class="sc-value" style="color:var(--accent);font-size:1.4em;">1.5~3초</div>
        <div class="sc-sub">결과/임팩트 먼저 보여주기</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">컷 전환</div>
        <div class="sc-value" style="color:var(--cyan);font-size:1.4em;">1~2초</div>
        <div class="sc-sub">빠른 템포 유지</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">전체 길이</div>
        <div class="sc-value" style="color:var(--yellow);font-size:1.4em;">20~35초</div>
        <div class="sc-sub">완시청률 최적화</div>
      </div>
      <div class="stat-card">
        <div class="sc-label">TTS 속도</div>
        <div class="sc-value" style="color:var(--green);font-size:1.4em;">280~320</div>
        <div class="sc-sub">분당 글자수</div>
      </div>
    </div>
  `;
}

// ─── Ideas (Video Bank) ───
async function loadIdeas(page = 1) {
  const s = state.videos;
  s.page = page;

  const params = new URLSearchParams({
    page, limit: 20, sort: s.sort,
    ...(s.topic !== 'all' && { topic: s.topic }),
    ...(s.search && { search: s.search })
  });

  const [data, topics] = await Promise.all([
    api(`/api/videos?${params}`),
    state.topics.length ? Promise.resolve(state.topics) : api('/api/topics')
  ]);

  state.topics = topics;
  s.data = data.videos;
  s.total = data.total;

  const el = document.getElementById('page-ideas');
  el.innerHTML = `
    <div class="filter-bar">
      <input type="text" id="searchInput" placeholder="영상 제목 검색..."
             value="${s.search}" oninput="debounceSearch(this.value)">
      <select id="sortSelect" onchange="state.videos.sort=this.value;loadIdeas();">
        <option value="views_desc" ${s.sort==='views_desc'?'selected':''}>조회수 높은순</option>
        <option value="views_asc" ${s.sort==='views_asc'?'selected':''}>조회수 낮은순</option>
        <option value="newest" ${s.sort==='newest'?'selected':''}>최신순</option>
        <option value="title_asc" ${s.sort==='title_asc'?'selected':''}>제목순</option>
      </select>
    </div>

    <div class="topic-chips">
      <button class="topic-chip ${s.topic==='all'?'active':''}" onclick="filterByTopic('all')">전체 (${s.topic==='all'?data.total:state.topics.reduce((a,t)=>a+t.count,0)})</button>
      ${state.topics.map(t => `
        <button class="topic-chip ${s.topic===t.topic?'active':''}" onclick="filterByTopic('${t.topic}')">
          ${t.topic} (${t.count})
        </button>
      `).join('')}
    </div>

    <div class="video-grid" id="videoGrid">
      ${data.videos.map(v => videoCardHTML(v)).join('')}
    </div>

    ${paginationHTML(data.page, data.pages, 'loadIdeas')}
  `;
}

function videoCardHTML(v) {
  const hasTranscript = v.transcript && v.transcript.length > 0;
  const urlAttr = v.url ? `data-url="${escHTML(v.url)}"` : '';
  return `
    <div class="video-card" ${urlAttr}>
      <div class="vc-body">
        <div class="vc-title">${escHTML(v.title)}</div>
        <div class="vc-meta">
          <span class="vc-views">👁 ${v.views_text || formatViews(v.views_num) + '회'}</span>
          <span class="vc-topic">${v.topic}</span>
          <span class="vc-duration">⏱ ${v.duration}</span>
          ${v.plan_count > 0 ? `<span class="vc-planned">✅ ${v.plan_count}개 기획</span>` : ''}
          ${hasTranscript ? '<span class="vc-transcribed">📝 전사완료</span>' : ''}
        </div>
        <div class="vc-actions">
          <button class="vc-btn transcribe ${hasTranscript ? 'done' : ''}" onclick="event.stopPropagation();transcribeVideo(${v.id}, '${escHTML(v.url || '')}')">${hasTranscript ? '📝 분석보기' : '🎙 전사하기'}</button>
          <button class="vc-btn reels" onclick="event.stopPropagation();openCreatePlan(${v.id},'reels')">릴스</button>
          <button class="vc-btn card" onclick="event.stopPropagation();openCreatePlan(${v.id},'card_news')">카드뉴스</button>
          <button class="vc-btn story" onclick="event.stopPropagation();openCreatePlan(${v.id},'story')">스토리</button>
        </div>
      </div>
    </div>
  `;
}

// ─── 전사 & 분석 ───
async function transcribeVideo(videoId, videoUrl) {
  // 기존 전사 결과 확인
  const existing = await api(`/api/videos/${videoId}/transcript`);
  if (existing.has_transcript) {
    showTranscriptModal(videoId, existing.transcript, existing.analysis);
    return;
  }

  // YouTube 영상 새 탭으로 열고 수동 입력 모달 표시
  if (videoUrl) {
    window.open(videoUrl, '_blank');
  }
  showManualTranscriptModal(videoId);
}

function showTranscriptModal(videoId, transcript, analysis) {
  const mc = document.getElementById('modalContent');

  const analysisHTML = analysis ? `
    <div class="transcript-analysis">
      <div class="ta-section">
        <h4>핵심 팩트</h4>
        <ul>${(analysis.key_facts || []).map(f => `<li>${escHTML(f)}</li>`).join('')}</ul>
      </div>
      ${analysis.hook_candidates ? `
        <div class="ta-section">
          <h4>후킹 후보</h4>
          <ul>${analysis.hook_candidates.map(h => `<li class="hook-item">${escHTML(h)}</li>`).join('')}</ul>
        </div>` : ''}
      ${analysis.product_names?.length ? `
        <div class="ta-section">
          <h4>제품/기술</h4>
          <div class="tag-list">${analysis.product_names.map(p => `<span class="tag">${escHTML(p)}</span>`).join('')}</div>
        </div>` : ''}
      ${analysis.reels_ideas?.length ? `
        <div class="ta-section">
          <h4>릴스 아이디어</h4>
          ${analysis.reels_ideas.map(r => `
            <div class="idea-card">
              <span class="idea-style">${r.style}</span>
              <strong>${escHTML(r.title || '')}</strong>
              <p>${escHTML(r.hook || '')}</p>
            </div>
          `).join('')}
        </div>` : ''}
      ${analysis.summary ? `
        <div class="ta-section">
          <h4>요약</h4>
          <p>${escHTML(analysis.summary)}</p>
        </div>` : ''}
      ${analysis.best_quotes?.length ? `
        <div class="ta-section">
          <h4>인용 가능 문구</h4>
          <ul>${analysis.best_quotes.map(q => `<li class="quote-item">"${escHTML(q)}"</li>`).join('')}</ul>
        </div>` : ''}
    </div>
  ` : '<p style="color:var(--text-dim);">분석 결과가 없습니다. Claude API 키가 설정되어 있으면 자동 분석됩니다.</p>';

  mc.innerHTML = `
    <div class="modal-title">📝 영상 전사 & 분석</div>
    <div style="display:flex;gap:8px;margin-bottom:16px;">
      <button class="btn btn-secondary tab-btn active" onclick="showTranscriptTab('analysis', this)">분석 결과</button>
      <button class="btn btn-secondary tab-btn" onclick="showTranscriptTab('transcript', this)">전사 텍스트</button>
      <button class="btn btn-primary" onclick="reanalyzeVideo(${videoId})" style="margin-left:auto;">🔄 재분석</button>
    </div>
    <div id="transcriptTabAnalysis">${analysisHTML}</div>
    <div id="transcriptTabTranscript" style="display:none;">
      <div class="transcript-text">${escHTML(transcript || '').replace(/\n/g, '<br>')}</div>
      <p style="color:var(--text-dim);font-size:0.8em;margin-top:8px;">${transcript ? transcript.length + '자' : ''}</p>
    </div>
  `;

  document.getElementById('modal').style.display = 'flex';
}

function showTranscriptTab(tab, btn) {
  document.getElementById('transcriptTabAnalysis').style.display = tab === 'analysis' ? '' : 'none';
  document.getElementById('transcriptTabTranscript').style.display = tab === 'transcript' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

async function reanalyzeVideo(videoId) {
  showToast('재분석 중...', 'info');
  try {
    const result = await api(`/api/videos/${videoId}/analyze`, {
      method: 'POST',
      body: {}
    });
    if (result.status === 'ok') {
      showToast('재분석 완료!', 'success');
      const tr = await api(`/api/videos/${videoId}/transcript`);
      showTranscriptModal(videoId, tr.transcript, tr.analysis);
    } else {
      showToast('재분석 실패: ' + (result.error || ''), 'error');
    }
  } catch (e) {
    showToast('재분석 오류: ' + e.message, 'error');
  }
}

function filterByTopic(topic) {
  state.videos.topic = topic;
  loadIdeas(1);
}

let searchTimer;
function debounceSearch(val) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.videos.search = val;
    loadIdeas(1);
  }, 300);
}

// ─── Create Plan Modal ───
function openCreatePlan(videoId, contentType) {
  const modal = document.getElementById('modal');
  const mc = document.getElementById('modalContent');

  const isReels = contentType === 'reels';

  mc.innerHTML = `
    <div class="modal-title">${contentType === 'reels' ? '릴스' : contentType === 'card_news' ? '카드뉴스' : '스토리'} 기획 생성</div>
    <div class="modal-row">
      <label>콘텐츠 제목 (수정 가능)</label>
      <input type="text" id="planTitle" placeholder="자동으로 영상 제목이 들어갑니다">
    </div>
    ${isReels ? `
    <div class="modal-row">
      <label>릴스 스타일</label>
      <div class="style-options" id="styleOptions">
        <div class="style-opt selected" data-style="kinetic_typo" onclick="selectStyle(this)">
          <div class="so-icon">⚡</div>
          <div class="so-label">키네틱 타이포</div>
          <div class="so-pct">주력 60%</div>
        </div>
        <div class="style-opt" data-style="before_after" onclick="selectStyle(this)">
          <div class="so-icon">↕️</div>
          <div class="so-label">Before/After</div>
          <div class="so-pct">20%</div>
        </div>
        <div class="style-opt" data-style="pov_chat" onclick="selectStyle(this)">
          <div class="so-icon">💬</div>
          <div class="so-label">POV 상황극</div>
          <div class="so-pct">20%</div>
        </div>
        <div class="style-opt" data-style="cartoon" onclick="selectStyle(this)">
          <div class="so-icon">🎨</div>
          <div class="so-label">카툰</div>
          <div class="so-pct">특별편</div>
        </div>
      </div>
    </div>
    ` : ''}
    <div class="modal-row">
      <label>후킹 텍스트 (첫 1.5초에 보여줄 문구)</label>
      <input type="text" id="planHook" placeholder="예: 와이파이 18배 빨라짐">
    </div>
    ${isReels ? `
    <div class="modal-row">
      <label>목표 길이 (초)</label>
      <input type="number" id="planDuration" value="25" min="15" max="60">
    </div>
    ` : ''}
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">취소</button>
      <button class="btn btn-primary" onclick="submitPlan(${videoId},'${contentType}')">생성</button>
    </div>
  `;
  modal.style.display = 'flex';
}

function selectStyle(el) {
  document.querySelectorAll('.style-opt').forEach(s => s.classList.remove('selected'));
  el.classList.add('selected');
}

async function submitPlan(videoId, contentType) {
  const title = document.getElementById('planTitle').value;
  const hook = document.getElementById('planHook').value;
  const styleEl = document.querySelector('.style-opt.selected');
  const style = styleEl ? styleEl.dataset.style : null;
  const durEl = document.getElementById('planDuration');
  const duration = durEl ? parseInt(durEl.value) : 25;

  try {
    await api('/api/plans', {
      method: 'POST',
      body: {
        video_id: videoId,
        content_type: contentType,
        reels_style: style,
        title: title || undefined,
        hook_text: hook || undefined,
        target_duration: duration
      }
    });
    closeModal();
    if (currentPage === 'ideas') loadIdeas(state.videos.page);
    else if (currentPage === 'plans') loadPlans();
    else if (currentPage === 'dashboard') loadDashboard();
  } catch (e) {
    alert('오류: ' + e.message);
  }
}

// ─── Plans ───
async function loadPlans(page = 1) {
  const data = await api(`/api/plans?page=${page}&limit=20`);
  state.plans.data = data.plans;
  state.plans.total = data.total;

  const el = document.getElementById('page-plans');

  if (data.plans.length === 0) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="es-icon">📋</div>
        <div class="es-text">아직 기획된 콘텐츠가 없어요</div>
        <p style="color:var(--text-dim);font-size:0.85em;margin-top:8px;">아이디어 뱅크에서 영상을 선택해 릴스/카드뉴스/스토리를 기획하세요</p>
        <button class="btn btn-primary" style="margin-top:16px;" onclick="navigate('ideas')">아이디어 뱅크 가기</button>
      </div>
    `;
    return;
  }

  el.innerHTML = `
    <div class="filter-bar">
      <select onchange="loadPlansFiltered(this.value)">
        <option value="">전체 상태</option>
        <option value="idea">아이디어</option>
        <option value="scripting">스크립트 작성중</option>
        <option value="editing">편집중</option>
        <option value="review">검토중</option>
        <option value="published">게시됨</option>
      </select>
    </div>
    <div class="plan-list">
      ${data.plans.map(p => `
        <div class="plan-item" onclick="openPlanDetail(${p.id})">
          <span class="plan-type-badge ${p.content_type}">
            ${p.content_type === 'reels' ? '릴스' : p.content_type === 'card_news' ? '카드뉴스' : '스토리'}
            ${p.reels_style ? ` · ${styleLabel(p.reels_style)}` : ''}
          </span>
          <div class="plan-info">
            <div class="plan-title">${escHTML(p.title)}</div>
            <div class="plan-sub">${p.topic || ''} · ${p.video_title ? escHTML(p.video_title).slice(0, 40) : ''}</div>
          </div>
          <span class="plan-status ${p.status}">${statusLabel(p.status)}</span>
        </div>
      `).join('')}
    </div>
    ${paginationHTML(data.page, Math.ceil(data.total / 20), 'loadPlans')}
  `;
}

async function loadPlansFiltered(status) {
  const params = status ? `?status=${status}&limit=20` : '?limit=20';
  const data = await api('/api/plans' + params);
  state.plans.data = data.plans;
  // Re-render list portion
  const listEl = document.querySelector('.plan-list');
  if (listEl) {
    listEl.innerHTML = data.plans.map(p => `
      <div class="plan-item" onclick="openPlanDetail(${p.id})">
        <span class="plan-type-badge ${p.content_type}">
          ${p.content_type === 'reels' ? '릴스' : p.content_type === 'card_news' ? '카드뉴스' : '스토리'}
          ${p.reels_style ? ` · ${styleLabel(p.reels_style)}` : ''}
        </span>
        <div class="plan-info">
          <div class="plan-title">${escHTML(p.title)}</div>
          <div class="plan-sub">${p.topic || ''}</div>
        </div>
        <span class="plan-status ${p.status}">${statusLabel(p.status)}</span>
      </div>
    `).join('');
  }
}

async function openPlanDetail(planId) {
  const plan = await api(`/api/plans/${planId}`);
  const mc = document.getElementById('modalContent');

  mc.innerHTML = `
    <div class="modal-title">기획 상세</div>
    <div style="display:flex;gap:8px;margin-bottom:14px;">
      <span class="plan-type-badge ${plan.content_type}">
        ${plan.content_type === 'reels' ? '릴스' : plan.content_type === 'card_news' ? '카드뉴스' : '스토리'}
      </span>
      ${plan.reels_style ? `<span class="badge">${styleLabel(plan.reels_style)}</span>` : ''}
      <span class="plan-status ${plan.status}">${statusLabel(plan.status)}</span>
    </div>
    <div class="modal-row">
      <label>제목</label>
      <input type="text" id="editTitle" value="${escAttr(plan.title || '')}">
    </div>
    <div class="modal-row">
      <label>후킹 텍스트</label>
      <input type="text" id="editHook" value="${escAttr(plan.hook_text || '')}">
    </div>
    <div class="modal-row">
      <label>상태</label>
      <select id="editStatus">
        ${['idea','scripting','editing','media_gen','compositing','review','scheduled','published']
          .map(s => `<option value="${s}" ${plan.status===s?'selected':''}>${statusLabel(s)}</option>`).join('')}
      </select>
    </div>
    <div class="modal-row">
      <label>원본 영상</label>
      <div style="font-size:0.85em;color:var(--text-dim);">
        ${escHTML(plan.video_title || '')}
        ${plan.video_url ? `<a href="${plan.video_url}" target="_blank" style="color:var(--cyan);margin-left:8px;">YouTube →</a>` : ''}
      </div>
    </div>
    ${plan.scenes && plan.scenes.length ? `
      <div class="section-title" style="margin-top:16px;">씬 목록 (${plan.scenes.length}개)</div>
      ${plan.scenes.map(s => `
        <div style="background:var(--surface2);border-radius:8px;padding:10px;margin-bottom:6px;">
          <div style="display:flex;gap:8px;align-items:center;font-size:0.8em;">
            <span style="color:var(--accent);font-family:'Do Hyeon';">#${s.scene_order}</span>
            <span class="badge">${s.scene_type}</span>
            <span style="color:var(--text-dim);">${s.duration_sec}초</span>
          </div>
          ${s.text_overlay ? `<div style="font-size:0.85em;margin-top:4px;">${escHTML(s.text_overlay)}</div>` : ''}
          ${s.narration ? `<div style="font-size:0.78em;color:var(--text-dim);margin-top:2px;">🎤 ${escHTML(s.narration)}</div>` : ''}
        </div>
      `).join('')}
    ` : ''}
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="deletePlan(${planId})" style="margin-right:auto;color:var(--accent);">삭제</button>
      <button class="btn btn-secondary" onclick="goToScript(${planId})" style="background:rgba(0,229,255,0.1);color:var(--cyan);border-color:var(--cyan);">✍️ 스크립트</button>
      <button class="btn btn-secondary" onclick="closeModal()">닫기</button>
      <button class="btn btn-primary" onclick="updatePlan(${planId})">저장</button>
    </div>
  `;
  document.getElementById('modal').style.display = 'flex';
}

async function updatePlan(planId) {
  await api(`/api/plans/${planId}`, {
    method: 'PATCH',
    body: {
      title: document.getElementById('editTitle').value,
      hook_text: document.getElementById('editHook').value,
      status: document.getElementById('editStatus').value
    }
  });
  closeModal();
  if (currentPage === 'plans') loadPlans();
  else if (currentPage === 'dashboard') loadDashboard();
}

async function deletePlan(planId) {
  if (!confirm('이 기획을 삭제할까요?')) return;
  await api(`/api/plans/${planId}`, { method: 'DELETE' });
  closeModal();
  if (currentPage === 'plans') loadPlans();
  else if (currentPage === 'dashboard') loadDashboard();
}

// ─── Script Editor ───
let scriptState = {
  plans: [],
  activePlanId: null,
  activePlan: null,
  scenes: [],
  generating: false,
  dirty: false
};

async function loadScriptEditor(selectPlanId) {
  const data = await api('/api/plans?limit=100');
  scriptState.plans = data.plans || [];

  const el = document.getElementById('page-script');

  if (scriptState.plans.length === 0) {
    el.innerHTML = `
      <div class="script-empty">
        <div class="se-icon">✍️</div>
        <div class="se-text">스크립트를 작성할 기획이 없어요</div>
        <p style="color:var(--text-dim);font-size:0.85em;margin-top:8px;">아이디어 뱅크에서 영상을 선택해 기획을 먼저 생성하세요</p>
        <button class="gen-btn primary" style="margin-top:16px;" onclick="navigate('ideas')">아이디어 뱅크 가기</button>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="script-layout">
      <div class="script-sidebar">
        <div class="ss-title">기획 목록</div>
        <div id="scriptPlanList"></div>
      </div>
      <div class="script-main" id="scriptMain">
        <div class="script-empty">
          <div class="se-icon">👈</div>
          <div class="se-text">왼쪽에서 기획을 선택하세요</div>
        </div>
      </div>
    </div>`;

  renderPlanList();

  if (selectPlanId) {
    selectScriptPlan(selectPlanId);
  }
}

function renderPlanList() {
  const container = document.getElementById('scriptPlanList');
  if (!container) return;

  container.innerHTML = scriptState.plans.map(p => {
    const typeColors = { reels: 'var(--accent)', card_news: 'var(--orange)', story: 'var(--purple)' };
    const typeLabels = { reels: '릴스', card_news: '카드뉴스', story: '스토리' };
    const isActive = scriptState.activePlanId === p.id;
    return `
      <div class="plan-select-item ${isActive ? 'active' : ''}" onclick="selectScriptPlan(${p.id})">
        <span class="psi-type" style="background:${typeColors[p.content_type]}22;color:${typeColors[p.content_type]};">
          ${typeLabels[p.content_type] || p.content_type}
          ${p.reels_style ? ' · ' + styleLabel(p.reels_style) : ''}
        </span>
        <div class="psi-title">${escHTML(p.title)}</div>
        <div class="psi-sub">${statusLabel(p.status)} · ${p.topic || ''}</div>
      </div>`;
  }).join('');
}

async function selectScriptPlan(planId) {
  if (scriptState.dirty && !confirm('저장하지 않은 변경사항이 있어요. 다른 기획으로 이동할까요?')) return;

  scriptState.activePlanId = planId;
  scriptState.dirty = false;

  const plan = await api(`/api/plans/${planId}`);
  scriptState.activePlan = plan;
  scriptState.scenes = (plan.scenes || []).map(s => ({...s}));

  renderPlanList();
  renderScriptMain();
}

function renderScriptMain() {
  const el = document.getElementById('scriptMain');
  const plan = scriptState.activePlan;
  if (!plan) return;

  const typeLabels = { reels: '릴스', card_news: '카드뉴스', story: '스토리' };
  const typeColors = { reels: 'var(--accent)', card_news: 'var(--orange)', story: 'var(--purple)' };
  const hasScenes = scriptState.scenes.length > 0;

  el.innerHTML = `
    <div class="script-header">
      <span class="sh-badge" style="background:${typeColors[plan.content_type]}22;color:${typeColors[plan.content_type]};">
        ${typeLabels[plan.content_type]}${plan.reels_style ? ' · ' + styleLabel(plan.reels_style) : ''}
      </span>
      <span class="sh-title">${escHTML(plan.title || '제목 없음')}</span>
      <span class="plan-status ${plan.status}" style="font-size:0.75em;">${statusLabel(plan.status)}</span>
      <button class="gen-btn primary" id="generateBtn" onclick="generateScript()" ${scriptState.generating ? 'disabled' : ''}>
        ${scriptState.generating ? '⏳ 생성중...' : '🤖 AI 스크립트 생성'}
      </button>
      ${hasScenes ? `
        <button class="gen-btn success" onclick="saveAllScenes()">💾 저장</button>
      ` : ''}
    </div>

    <div class="script-info-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <div>
        <label>후킹 텍스트</label>
        <input type="text" id="scriptHook" value="${escAttr(plan.hook_text || '')}"
               placeholder="첫 1.5초에 보여줄 후킹 문구" onchange="markDirty()">
      </div>
      <div>
        <label>캡션</label>
        <input type="text" id="scriptCaption" value="${escAttr(plan.caption || '')}"
               placeholder="인스타 캡션 (해시태그 포함)" onchange="markDirty()">
      </div>
    </div>

    ${plan.content_type === 'reels' && hasScenes ? renderDurationBar() : ''}

    <div class="scene-timeline" id="sceneTimeline">
      ${hasScenes ? scriptState.scenes.map((s, i) => renderSceneCard(s, i)).join('') : `
        <div class="script-empty" style="padding:40px;">
          <div class="se-icon">📝</div>
          <div class="se-text">아직 씬이 없어요</div>
          <p style="color:var(--text-dim);font-size:0.85em;margin-top:8px;">AI 스크립트 생성 버튼으로 자동 생성하거나, 직접 추가하세요</p>
        </div>
      `}
    </div>

    <button class="add-scene-btn" onclick="addNewScene()">+ 새 씬 추가</button>
  `;
}

function renderSceneCard(scene, idx) {
  const typeOptions = ['hook', 'normal', 'result', 'cta'].map(t =>
    `<option value="${t}" ${scene.scene_type === t ? 'selected' : ''}>${t}</option>`
  ).join('');

  return `
    <div class="scene-card" draggable="true"
         ondragstart="dragScene(event,${idx})" ondragover="event.preventDefault()"
         ondrop="dropScene(event,${idx})" data-idx="${idx}">
      <div class="sc-header">
        <span class="sc-drag" title="드래그로 순서 변경">⠿</span>
        <span class="sc-num">#${idx + 1}</span>
        <select class="sc-type-select" onchange="updateScene(${idx},'scene_type',this.value)">
          ${typeOptions}
        </select>
        <input type="number" class="sc-dur" value="${scene.duration_sec || 2}"
               step="0.5" min="0.5" max="30"
               onchange="updateScene(${idx},'duration_sec',parseFloat(this.value))"
               title="길이 (초)">
        <span style="font-size:0.72em;color:var(--text-dim);">초</span>
        <button class="sc-delete" onclick="deleteScene(${idx})" title="씬 삭제">✕</button>
      </div>
      <div class="sc-fields">
        <div class="sc-field">
          <label>텍스트 오버레이</label>
          <textarea rows="2" onchange="updateScene(${idx},'text_overlay',this.value)"
                    placeholder="화면에 표시될 텍스트">${escHTML(scene.text_overlay || '')}</textarea>
        </div>
        <div class="sc-field">
          <label>나레이션 (TTS)</label>
          <textarea rows="2" onchange="updateScene(${idx},'narration',this.value)"
                    placeholder="음성으로 읽을 텍스트">${escHTML(scene.narration || '')}</textarea>
        </div>
        <div class="sc-field sc-field-full">
          <label>비주얼 설명</label>
          <input type="text" value="${escAttr(scene.visual_desc || '')}"
                 onchange="updateScene(${idx},'visual_desc',this.value)"
                 placeholder="배경 영상/이미지 설명">
        </div>
      </div>
      <div id="spell-${idx}"></div>
    </div>`;
}

function renderDurationBar() {
  const total = scriptState.scenes.reduce((s, sc) => s + (sc.duration_sec || 0), 0);
  const min = 20, max = 35;
  const pct = Math.min(100, (total / max) * 100);
  let color = 'var(--green)';
  if (total < min) color = 'var(--yellow)';
  if (total > max) color = 'var(--accent)';

  return `
    <div class="total-duration-bar">
      <span class="tdb-label">전체 길이</span>
      <span class="tdb-value" style="color:${color};">${total.toFixed(1)}초</span>
      <div class="tdb-bar">
        <div class="tdb-fill" style="width:${pct}%;background:${color};"></div>
      </div>
      <span class="tdb-label" style="font-size:0.7em;">${min}~${max}초 권장</span>
    </div>`;
}

function updateScene(idx, field, value) {
  scriptState.scenes[idx][field] = value;
  scriptState.dirty = true;

  // 나레이션이나 텍스트 수정 시 맞춤법 체크
  if (field === 'narration' || field === 'text_overlay') {
    checkSceneSpelling(idx, value);
  }

  // duration 변경 시 bar 업데이트
  if (field === 'duration_sec' && scriptState.activePlan.content_type === 'reels') {
    const barContainer = document.querySelector('.total-duration-bar');
    if (barContainer) {
      barContainer.outerHTML = renderDurationBar();
    }
  }
}

async function checkSceneSpelling(idx, text) {
  if (!text || text.length < 2) {
    const el = document.getElementById(`spell-${idx}`);
    if (el) el.innerHTML = '';
    return;
  }
  try {
    const result = await api('/api/check-spelling', {
      method: 'POST',
      body: { text }
    });
    const el = document.getElementById(`spell-${idx}`);
    if (el && result.issues && result.issues.length > 0) {
      el.innerHTML = result.issues.map(i =>
        `<div class="spell-issue">
          ⚠️ ${i.description}
          <span class="si-fix" onclick="applySpellFix(${idx},'${i.pattern}','${i.suggestion}')">자동 수정</span>
        </div>`
      ).join('');
    } else if (el) {
      el.innerHTML = '';
    }
  } catch (e) { /* ignore */ }
}

function applySpellFix(idx, pattern, fix) {
  const scene = scriptState.scenes[idx];
  const regex = new RegExp(pattern, 'g');
  if (scene.narration) scene.narration = scene.narration.replace(regex, fix);
  if (scene.text_overlay) scene.text_overlay = scene.text_overlay.replace(regex, fix);
  scriptState.dirty = true;
  renderScriptMain();
}

function addNewScene() {
  const newOrder = scriptState.scenes.length + 1;
  scriptState.scenes.push({
    scene_order: newOrder,
    scene_type: 'normal',
    duration_sec: 2.0,
    narration: '',
    visual_desc: '',
    text_overlay: ''
  });
  scriptState.dirty = true;
  renderScriptMain();
}

function deleteScene(idx) {
  if (!confirm(`씬 #${idx + 1}을 삭제할까요?`)) return;
  scriptState.scenes.splice(idx, 1);
  // Reorder
  scriptState.scenes.forEach((s, i) => s.scene_order = i + 1);
  scriptState.dirty = true;
  renderScriptMain();
}

// Drag & drop
let dragIdx = null;
function dragScene(e, idx) {
  dragIdx = idx;
  e.dataTransfer.effectAllowed = 'move';
}
function dropScene(e, targetIdx) {
  e.preventDefault();
  if (dragIdx === null || dragIdx === targetIdx) return;
  const [moved] = scriptState.scenes.splice(dragIdx, 1);
  scriptState.scenes.splice(targetIdx, 0, moved);
  scriptState.scenes.forEach((s, i) => s.scene_order = i + 1);
  scriptState.dirty = true;
  dragIdx = null;
  renderScriptMain();
}

async function generateScript() {
  if (scriptState.generating) return;
  scriptState.generating = true;

  const btn = document.getElementById('generateBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ AI 생성중...'; }

  try {
    const result = await api('/api/generate-script', {
      method: 'POST',
      body: { plan_id: scriptState.activePlanId }
    });

    if (result.status === 'ok' || result.status === 'fallback') {
      // 새로 로드
      const plan = await api(`/api/plans/${scriptState.activePlanId}`);
      scriptState.activePlan = plan;
      scriptState.scenes = (plan.scenes || []).map(s => ({...s}));

      if (result.script && result.script.caption) {
        scriptState.activePlan.caption = result.script.caption;
      }
      if (result.script && result.script.hook_text) {
        scriptState.activePlan.hook_text = result.script.hook_text;
      }

      scriptState.dirty = false;
      renderScriptMain();

      if (result.status === 'fallback') {
        showToast('템플릿으로 생성됨 (API 키 없음)', 'warn');
      } else {
        showToast(`스크립트 생성 완료! (${result.scenes_count}씬)`, 'success');
      }
    } else {
      showToast('생성 실패: ' + (result.message || ''), 'error');
    }
  } catch (e) {
    showToast('오류: ' + e.message, 'error');
  }

  scriptState.generating = false;
  const btn2 = document.getElementById('generateBtn');
  if (btn2) { btn2.disabled = false; btn2.textContent = '🤖 AI 스크립트 생성'; }
}

async function saveAllScenes() {
  const planId = scriptState.activePlanId;
  if (!planId) return;

  try {
    // 씬 일괄 저장
    await api(`/api/plans/${planId}/scenes/bulk`, {
      method: 'PUT',
      body: {
        scenes: scriptState.scenes.map((s, i) => ({
          scene_order: i + 1,
          scene_type: s.scene_type || 'normal',
          duration_sec: s.duration_sec || 2.0,
          narration: s.narration || null,
          visual_desc: s.visual_desc || null,
          text_overlay: s.text_overlay || null
        }))
      }
    });

    // hook_text, caption 저장
    const hookEl = document.getElementById('scriptHook');
    const captionEl = document.getElementById('scriptCaption');
    const updates = {};
    if (hookEl) updates.hook_text = hookEl.value;
    if (captionEl) updates.caption = captionEl.value;

    if (Object.keys(updates).length > 0) {
      await api(`/api/plans/${planId}`, { method: 'PATCH', body: updates });
    }

    scriptState.dirty = false;
    showToast('저장 완료!', 'success');
  } catch (e) {
    showToast('저장 실패: ' + e.message, 'error');
  }
}

function markDirty() {
  scriptState.dirty = true;
}

// Toast notification
function showToast(msg, type = 'info') {
  const existing = document.getElementById('toast');
  if (existing) existing.remove();

  const colors = { success: 'var(--green)', error: 'var(--accent)', warn: 'var(--yellow)', info: 'var(--cyan)' };
  const toast = document.createElement('div');
  toast.id = 'toast';
  toast.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:200;
    background:var(--surface);border:1px solid ${colors[type] || colors.info};
    color:${colors[type] || colors.info};
    padding:12px 20px;border-radius:10px;font-size:0.88em;
    font-family:'Do Hyeon';box-shadow:0 4px 20px rgba(0,0,0,0.4);
    animation:fadeIn 0.2s;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Navigate to script editor from plan detail
function goToScript(planId) {
  closeModal();
  navigate('script');
  setTimeout(() => selectScriptPlan(planId), 200);
}

// ─── Media Generation ───
let mediaState = { plans: [], activePlanId: null, generating: false };

async function loadMediaPage() {
  const data = await api('/api/plans?limit=100');
  // 스크립트가 있는 기획만 (scripting 이상 상태)
  mediaState.plans = (data.plans || []).filter(p =>
    ['scripting','editing','media_gen','compositing','review','scheduled','published'].includes(p.status)
  );

  const el = document.getElementById('page-media');

  if (mediaState.plans.length === 0) {
    el.innerHTML = `
      <div class="script-empty">
        <div class="se-icon">🎬</div>
        <div class="se-text">미디어를 생성할 기획이 없어요</div>
        <p style="color:var(--text-dim);font-size:0.85em;margin-top:8px;">
          먼저 스크립트 에디터에서 스크립트를 생성하세요
        </p>
        <button class="gen-btn primary" style="margin-top:16px;" onclick="navigate('script')">스크립트 에디터 가기</button>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="section-title">🎬 미디어 생성 대시보드</div>
    <p style="color:var(--text-dim);font-size:0.85em;margin-bottom:16px;">
      스크립트가 준비된 기획을 선택하면 TTS, 이미지, 영상을 자동 생성합니다.
      API 키가 없으면 placeholder로 대체됩니다.
    </p>

    <div class="section-title" style="margin-top:20px;">🔑 API 키 설정 (선택)</div>
    <div class="script-info-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
      <div>
        <label>ElevenLabs API Key</label>
        <input type="password" id="keyElevenlabs" placeholder="sk-..." autocomplete="off">
      </div>
      <div>
        <label>Together AI API Key (FLUX)</label>
        <input type="password" id="keyTogether" placeholder="..." autocomplete="off">
      </div>
      <div>
        <label>OpenAI API Key (DALL-E 3)</label>
        <input type="password" id="keyOpenai" placeholder="sk-..." autocomplete="off">
      </div>
      <div>
        <label>MiniMax API Key (Video)</label>
        <input type="password" id="keyMinimax" placeholder="..." autocomplete="off">
      </div>
    </div>

    <div class="section-title">📋 미디어 생성 가능 기획</div>
    <div class="plan-list" id="mediaPlans">
      ${mediaState.plans.map(p => mediaPlanItemHTML(p)).join('')}
    </div>
  `;
}

function mediaPlanItemHTML(p) {
  const typeLabels = { reels: '릴스', card_news: '카드뉴스', story: '스토리' };
  const typeColors = { reels: 'var(--accent)', card_news: 'var(--orange)', story: 'var(--purple)' };
  return `
    <div class="plan-item" style="flex-wrap:wrap;">
      <span class="plan-type-badge ${p.content_type}">
        ${typeLabels[p.content_type]}
        ${p.reels_style ? ' · ' + styleLabel(p.reels_style) : ''}
      </span>
      <div class="plan-info">
        <div class="plan-title">${escHTML(p.title)}</div>
        <div class="plan-sub">${statusLabel(p.status)} · ${p.topic || ''}</div>
      </div>
      <button class="gen-btn primary" id="mediaBtn-${p.id}"
              onclick="startMediaGen(${p.id})" ${mediaState.generating ? 'disabled' : ''}>
        🎬 미디어 생성
      </button>
      <button class="gen-btn secondary" onclick="checkMediaStatus(${p.id})">
        📁 상태 확인
      </button>
    </div>`;
}

async function startMediaGen(planId) {
  if (mediaState.generating) {
    showToast('이미 생성 중입니다', 'warn');
    return;
  }

  mediaState.generating = true;
  const btn = document.getElementById(`mediaBtn-${planId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 생성중...'; }

  const apiKeys = {
    elevenlabs: document.getElementById('keyElevenlabs')?.value || '',
    together: document.getElementById('keyTogether')?.value || '',
    openai: document.getElementById('keyOpenai')?.value || '',
    minimax: document.getElementById('keyMinimax')?.value || '',
    image_provider: document.getElementById('keyTogether')?.value ? 'together' :
                    document.getElementById('keyOpenai')?.value ? 'openai' : 'placeholder'
  };

  try {
    const result = await api('/api/generate-media', {
      method: 'POST',
      body: { plan_id: planId, api_keys: apiKeys }
    });

    if (result.status === 'ok') {
      showToast(`미디어 생성 완료! (${result.duration || 0}초)`, 'success');
    } else if (result.status === 'placeholder') {
      showToast('Placeholder로 생성됨 (API 키 미설정)', 'warn');
    } else {
      showToast('생성 실패: ' + (result.error || ''), 'error');
    }
  } catch (e) {
    showToast('오류: ' + e.message, 'error');
  }

  mediaState.generating = false;
  if (btn) { btn.disabled = false; btn.textContent = '🎬 미디어 생성'; }
}

async function checkMediaStatus(planId) {
  try {
    const result = await api(`/api/media/${planId}/status`);
    const mc = document.getElementById('modalContent');

    mc.innerHTML = `
      <div class="modal-title">미디어 파일 상태</div>
      <div style="margin-bottom:12px;">
        <span class="badge" style="background:var(--green)22;color:var(--green);">
          ${result.status === 'generated' ? '생성됨' : '미생성'}
        </span>
        <span style="font-size:0.8em;color:var(--text-dim);margin-left:8px;">
          ${result.files?.length || 0}개 파일
        </span>
      </div>
      ${result.files?.length ? `
        <div style="display:flex;flex-direction:column;gap:6px;">
          ${result.files.map(f => `
            <div style="background:var(--surface2);border-radius:8px;padding:10px;display:flex;align-items:center;gap:8px;">
              <span style="font-size:1.2em;">${f.type === 'mp4' ? '🎬' : f.type === 'wav' ? '🎤' : f.type === 'png' ? '🖼️' : '📄'}</span>
              <span style="flex:1;font-size:0.85em;">${f.name}</span>
              <span style="font-size:0.72em;color:var(--text-dim);">${(f.size/1024).toFixed(1)}KB</span>
            </div>
          `).join('')}
        </div>
      ` : '<p style="color:var(--text-dim);font-size:0.85em;">아직 생성된 파일이 없습니다.</p>'}
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeModal()">닫기</button>
      </div>
    `;
    document.getElementById('modal').style.display = 'flex';
  } catch (e) {
    showToast('상태 확인 실패: ' + e.message, 'error');
  }
}

// ─── Publish & Schedule ───
async function loadPublishPage() {
  const [plansData, schedulesData] = await Promise.all([
    api('/api/plans?limit=100'),
    api('/api/schedules')
  ]);

  // media_gen 이상 상태의 기획만
  const readyPlans = (plansData.plans || []).filter(p =>
    ['media_gen','compositing','review','scheduled','published'].includes(p.status)
  );
  const schedules = schedulesData.schedules || [];

  const el = document.getElementById('page-publish');

  el.innerHTML = `
    <div class="section-title">🔑 Instagram API 설정</div>
    <div class="script-info-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
      <div>
        <label>Instagram Access Token</label>
        <input type="password" id="igToken" placeholder="EAAxxxxxxx..." autocomplete="off">
      </div>
      <div>
        <label>Instagram User ID</label>
        <input type="text" id="igUserId" placeholder="17841400000000" autocomplete="off">
      </div>
    </div>
    <button class="gen-btn secondary" onclick="checkIgAccount()" style="margin-bottom:24px;">
      🔍 계정 확인
    </button>
    <div id="igAccountInfo"></div>

    <div class="section-title" style="margin-top:24px;">📅 스케줄 캘린더</div>
    <div style="display:flex;gap:8px;margin-bottom:16px;">
      <button class="gen-btn secondary" onclick="suggestSchedule()">🤖 최적 시간 추천</button>
    </div>
    <div id="scheduleList">
      ${schedules.length ? schedules.map(s => scheduleItemHTML(s)).join('') : `
        <div class="empty-state" style="padding:30px;">
          <div class="es-icon">📅</div>
          <div class="es-text">스케줄이 없어요</div>
        </div>
      `}
    </div>

    <div class="section-title" style="margin-top:24px;">📤 업로드 가능 콘텐츠</div>
    ${readyPlans.length ? `
      <div class="plan-list" id="publishPlans">
        ${readyPlans.map(p => publishPlanItemHTML(p)).join('')}
      </div>
    ` : `
      <div class="empty-state" style="padding:30px;">
        <div class="es-icon">🎬</div>
        <div class="es-text">업로드 가능한 콘텐츠가 없어요</div>
        <p style="color:var(--text-dim);font-size:0.85em;margin-top:8px;">미디어 생성을 먼저 완료하세요</p>
      </div>
    `}
  `;
}

function scheduleItemHTML(s) {
  const dt = new Date(s.scheduled_at);
  const dateStr = `${dt.getMonth()+1}/${dt.getDate()} (${['일','월','화','수','목','금','토'][dt.getDay()]}) ${dt.getHours()}:${String(dt.getMinutes()).padStart(2,'0')}`;
  const statusColors = {
    scheduled: 'var(--cyan)', publishing: 'var(--yellow)',
    published: 'var(--green)', failed: 'var(--accent)', cancelled: 'var(--text-dim)'
  };
  const statusLabels2 = {
    scheduled: '예약됨', publishing: '게시중',
    published: '게시됨', failed: '실패', cancelled: '취소됨'
  };
  const typeLabels = { reels: '릴스', card_news: '카드뉴스', story: '스토리' };

  return `
    <div class="plan-item" style="margin-bottom:6px;">
      <span style="font-family:'Do Hyeon';color:var(--cyan);font-size:0.9em;min-width:120px;">${dateStr}</span>
      <span class="plan-type-badge ${s.content_type || ''}">
        ${typeLabels[s.content_type] || ''}${s.reels_style ? ' · ' + styleLabel(s.reels_style) : ''}
      </span>
      <div class="plan-info">
        <div class="plan-title">${escHTML(s.title || '')}</div>
      </div>
      <span style="padding:3px 10px;border-radius:12px;font-size:0.72em;font-family:'Do Hyeon';
            background:${statusColors[s.status]}22;color:${statusColors[s.status]};">
        ${statusLabels2[s.status] || s.status}
      </span>
      ${s.status === 'scheduled' ? `
        <button class="gen-btn secondary" style="font-size:0.75em;padding:4px 10px;"
                onclick="cancelSchedule(${s.id})">취소</button>
      ` : ''}
    </div>`;
}

function publishPlanItemHTML(p) {
  const typeLabels = { reels: '릴스', card_news: '카드뉴스', story: '스토리' };
  return `
    <div class="plan-item" style="flex-wrap:wrap;">
      <span class="plan-type-badge ${p.content_type}">
        ${typeLabels[p.content_type]}${p.reels_style ? ' · ' + styleLabel(p.reels_style) : ''}
      </span>
      <div class="plan-info">
        <div class="plan-title">${escHTML(p.title)}</div>
        <div class="plan-sub">${statusLabel(p.status)}</div>
      </div>
      <button class="gen-btn secondary" onclick="openScheduleModal(${p.id},'${escAttr(p.title)}')">
        📅 스케줄
      </button>
      <button class="gen-btn primary" onclick="directUpload(${p.id})">
        📤 즉시 업로드
      </button>
    </div>`;
}

async function checkIgAccount() {
  const token = document.getElementById('igToken')?.value;
  const userId = document.getElementById('igUserId')?.value;

  if (!token || !userId) {
    showToast('토큰과 User ID를 입력하세요', 'warn');
    return;
  }

  try {
    const result = await api(`/api/instagram/account?access_token=${encodeURIComponent(token)}&ig_user_id=${userId}`);
    const info = document.getElementById('igAccountInfo');
    if (result.status === 'ok' && result.account) {
      const a = result.account;
      info.innerHTML = `
        <div class="stat-card" style="display:inline-flex;gap:16px;align-items:center;margin-bottom:16px;">
          <div style="font-family:'Black Han Sans';font-size:1.2em;color:var(--accent);">@${a.username}</div>
          <div style="font-size:0.85em;">팔로워 ${(a.followers_count||0).toLocaleString()}</div>
          <div style="font-size:0.85em;">게시물 ${a.media_count||0}</div>
          <span style="color:var(--green);font-size:0.85em;">✓ 연결됨</span>
        </div>`;
      showToast('Instagram 계정 연결됨!', 'success');
    } else {
      info.innerHTML = `<p style="color:var(--accent);font-size:0.85em;">${result.error || '연결 실패'}</p>`;
    }
  } catch (e) {
    showToast('계정 확인 실패: ' + e.message, 'error');
  }
}

function openScheduleModal(planId, title) {
  const mc = document.getElementById('modalContent');
  const now = new Date();
  const defaultDt = new Date(now.getTime() + 3600000); // 1시간 후
  const dtStr = defaultDt.toISOString().slice(0, 16);

  mc.innerHTML = `
    <div class="modal-title">📅 게시 스케줄 설정</div>
    <p style="font-size:0.85em;color:var(--text-dim);margin-bottom:12px;">${escHTML(title)}</p>
    <div class="modal-row">
      <label>게시 예정 시간</label>
      <input type="datetime-local" id="scheduleTime" value="${dtStr}">
    </div>
    <div style="background:var(--surface2);border-radius:8px;padding:10px;margin-top:8px;">
      <div style="font-size:0.78em;color:var(--text-dim);margin-bottom:6px;">🤖 추천 시간대</div>
      <div style="font-size:0.82em;">릴스: 18:00~21:00 · 카드뉴스: 12:00~14:00 · 스토리: 07:00~09:00</div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">취소</button>
      <button class="btn btn-primary" onclick="createSchedule(${planId})">스케줄 등록</button>
    </div>
  `;
  document.getElementById('modal').style.display = 'flex';
}

async function createSchedule(planId) {
  const dt = document.getElementById('scheduleTime')?.value;
  if (!dt) { showToast('시간을 선택하세요', 'warn'); return; }

  try {
    await api('/api/schedules', {
      method: 'POST',
      body: { plan_id: planId, scheduled_at: new Date(dt).toISOString() }
    });
    closeModal();
    showToast('스케줄 등록 완료!', 'success');
    loadPublishPage();
  } catch (e) {
    showToast('등록 실패: ' + e.message, 'error');
  }
}

async function cancelSchedule(scheduleId) {
  if (!confirm('이 스케줄을 취소할까요?')) return;
  await api(`/api/schedules/${scheduleId}`, { method: 'DELETE' });
  showToast('스케줄 취소됨', 'info');
  loadPublishPage();
}

async function suggestSchedule() {
  try {
    const result = await api('/api/schedules/suggest', {
      method: 'POST',
      body: { count: 7 }
    });

    const mc = document.getElementById('modalContent');
    mc.innerHTML = `
      <div class="modal-title">🤖 최적 게시 시간 추천</div>
      <p style="font-size:0.82em;color:var(--text-dim);margin-bottom:12px;">
        인스타그램 IT 콘텐츠 기준 최적 시간대입니다.
      </p>
      <div style="display:flex;flex-direction:column;gap:6px;">
        ${(result.suggestions || []).map(s => `
          <div style="background:var(--surface2);border-radius:8px;padding:10px;display:flex;align-items:center;gap:12px;">
            <span style="font-family:'Do Hyeon';color:var(--cyan);min-width:90px;">
              ${s.day}요일 ${s.time}
            </span>
            <span style="font-size:0.8em;color:var(--text-dim);">
              ${s.datetime.split('T')[0]}
            </span>
            ${s.is_weekend ? '<span style="font-size:0.7em;background:rgba(255,214,10,0.1);color:var(--yellow);padding:2px 6px;border-radius:4px;">주말</span>' : ''}
          </div>
        `).join('')}
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeModal()">닫기</button>
      </div>
    `;
    document.getElementById('modal').style.display = 'flex';
  } catch (e) {
    showToast('추천 실패: ' + e.message, 'error');
  }
}

async function directUpload(planId) {
  const token = document.getElementById('igToken')?.value;
  const userId = document.getElementById('igUserId')?.value;

  if (!token || !userId) {
    showToast('Instagram API 토큰과 User ID를 먼저 입력하세요', 'warn');
    return;
  }

  const mediaUrl = prompt('외부 호스팅된 미디어 URL을 입력하세요.\n(릴스: 영상 URL, 카드뉴스: 이미지 URL 콤마 구분)');
  if (!mediaUrl) return;

  try {
    const result = await api('/api/instagram/upload', {
      method: 'POST',
      body: {
        plan_id: planId,
        access_token: token,
        ig_user_id: userId,
        media_url: mediaUrl
      }
    });

    if (result.status === 'ok') {
      showToast(`게시 완료! Media ID: ${result.media_id}`, 'success');
      loadPublishPage();
    } else {
      showToast('게시 실패: ' + (result.error || ''), 'error');
    }
  } catch (e) {
    showToast('업로드 오류: ' + e.message, 'error');
  }
}

// ─── Templates ───
async function loadTemplates() {
  const rules = await api('/api/tempo-rules');
  const el = document.getElementById('page-templates');

  const grouped = {};
  rules.forEach(r => {
    const key = r.reels_style ? `${r.content_type}:${r.reels_style}` : r.content_type;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(r);
  });

  const groupLabels = {
    'reels': '릴스 공통',
    'reels:kinetic_typo': '릴스 · 키네틱 타이포',
    'reels:before_after': '릴스 · Before/After',
    'reels:pov_chat': '릴스 · POV 상황극',
    'card_news': '카드뉴스',
    'story': '스토리',
    'all': '톤 & 매너 (전체 공통)'
  };

  el.innerHTML = Object.entries(grouped).map(([key, items]) => `
    <div class="section-title" style="margin-top:20px;">${groupLabels[key] || key}</div>
    <div class="rules-grid">
      ${items.map(r => `
        <div class="rule-card">
          <div class="rc-header">
            <span class="rc-name">${r.rule_name}</span>
          </div>
          <div class="rc-value">${r.rule_value}</div>
          <div class="rc-desc">${r.description || ''}</div>
        </div>
      `).join('')}
    </div>
  `).join('');
}

// ─── Modal ───
function closeModal() {
  document.getElementById('modal').style.display = 'none';
}

// ─── Helpers ───
function formatViews(n) {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '만';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + '천';
  return n.toLocaleString();
}

function styleLabel(s) {
  const map = { kinetic_typo: '키네틱 타이포', before_after: 'Before/After', pov_chat: 'POV 상황극', cartoon: '카툰' };
  return map[s] || s;
}

function statusLabel(s) {
  const map = {
    idea: '아이디어', scripting: '스크립트', editing: '편집중',
    media_gen: '미디어 생성', compositing: '합성중',
    review: '검토중', scheduled: '예약됨', published: '게시됨'
  };
  return map[s] || s;
}

function escHTML(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function escAttr(s) {
  return (s || '').replace(/"/g, '&quot;');
}

function paginationHTML(current, total, fn) {
  if (total <= 1) return '';
  let html = '<div class="pagination">';
  if (current > 1) html += `<button onclick="${fn}(${current - 1})">‹</button>`;
  const start = Math.max(1, current - 2);
  const end = Math.min(total, current + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === current ? 'active' : ''}" onclick="${fn}(${i})">${i}</button>`;
  }
  if (current < total) html += `<button onclick="${fn}(${current + 1})">›</button>`;
  html += '</div>';
  return html;
}

// ─── Manual Transcript Paste ───
function showManualTranscriptModal(videoId) {
  const mc = document.getElementById('modalContent');
  mc.innerHTML = `
    <h3 style="margin-bottom:12px;">📝 자막 입력</h3>
    <p style="color:var(--text-dim);font-size:0.9em;line-height:1.6;margin-bottom:12px;">
      YouTube 영상이 새 탭에서 열렸습니다.<br>
      아래 방법으로 자막을 복사하여 붙여넣어 주세요.
    </p>
    <div style="background:var(--bg-dark);padding:12px;border-radius:8px;margin-bottom:16px;font-size:0.85em;line-height:1.7;">
      <strong>자막 복사 방법:</strong><br>
      1. 열린 YouTube 영상 아래 <strong>"...더보기"</strong> 클릭<br>
      2. <strong>"스크립트 표시"</strong> 클릭<br>
      3. 자막 전체를 <strong>Ctrl+A → Ctrl+C</strong> (Mac: ⌘A → ⌘C) 복사<br>
      4. 아래 입력창에 <strong>붙여넣기</strong>
    </div>
    <textarea id="manualTranscriptInput" placeholder="여기에 자막 텍스트를 붙여넣으세요..."
      style="width:100%;min-height:200px;background:var(--bg-dark);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:0.9em;resize:vertical;font-family:inherit;"></textarea>
    <div style="display:flex;gap:8px;margin-top:12px;align-items:center;">
      <button class="gen-btn primary" onclick="submitManualTranscript(${videoId})">✅ 저장 및 분석</button>
      <button class="btn btn-secondary" onclick="closeModal()">취소</button>
      <span id="manualTranscriptStatus" style="font-size:0.85em;margin-left:8px;"></span>
    </div>
  `;
  document.getElementById('modal').style.display = 'flex';
}

async function submitManualTranscript(videoId) {
  const textarea = document.getElementById('manualTranscriptInput');
  const text = textarea.value.trim();
  if (!text) {
    showToast('자막 텍스트를 입력해주세요.', 'error');
    return;
  }

  // 타임스탬프 제거 (YouTube 스크립트에서 복사하면 타임스탬프가 포함됨)
  const cleaned = text.replace(/^\d{1,2}:\d{2}(:\d{2})?\s*/gm, '').replace(/\n{2,}/g, '\n').trim();

  const statusEl = document.getElementById('manualTranscriptStatus');
  statusEl.textContent = '⏳ 저장 및 분석 중...';
  statusEl.style.color = 'var(--text-dim)';

  try {
    const result = await api(`/api/videos/${videoId}/transcribe-manual`, {
      method: 'POST',
      body: { transcript: cleaned }
    });

    if (result.status === 'ok') {
      showToast(`전사 완료! (${result.word_count}자)`, 'success');
      showTranscriptModal(videoId, result.transcript, result.analysis);
      if (currentPage === 'ideas') loadIdeas(state.videos.page);
    } else {
      statusEl.textContent = '❌ ' + (result.error || '저장 실패');
      statusEl.style.color = 'var(--red)';
    }
  } catch (e) {
    statusEl.textContent = '❌ 오류: ' + e.message;
    statusEl.style.color = 'var(--red)';
  }
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
});
