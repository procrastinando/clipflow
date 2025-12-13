let currentData = null;
let eventSource = null;

document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
    const storedKey = localStorage.getItem('groqKey');
    if(storedKey) document.getElementById('groq-key').value = storedKey;
});

function toggleApiKey() {
    const isChecked = document.getElementById('gen-subs').checked;

    const apiContainer = document.getElementById('api-input-container');
    apiContainer.style.display = isChecked ? 'block' : 'none';

    const translateBtn = document.getElementById('translate-subs');
    translateBtn.disabled = !isChecked;
    if (!isChecked) {
        translateBtn.checked = false;
    }
}

function changeSlide(stepIndex) {
    document.querySelectorAll('.slide').forEach((el, index) => {
        el.classList.remove('active');
        if (index + 1 === stepIndex) el.classList.add('active');
    });
}

function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if(h > 0) return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
    return `${m}:${s.toString().padStart(2,'0')}`;
}

async function fetchInfo() {
    const url = document.getElementById('youtube-url').value;
    const btn = document.getElementById('btn-next');
    
    if(!url) return alert("Please enter a URL");
    
    btn.innerHTML = '<div class="spinner" style="width:20px;height:20px;border-width:2px;margin:0;"></div>';
    
    try {
        const response = await fetch('/api/info', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        });
        
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        
        currentData = data;
        
        document.getElementById('video-title').textContent = data.title;
        document.getElementById('video-duration').textContent = formatDuration(data.duration);
        document.getElementById('thumb-preview').src = data.thumbnail;
        
        const vSelect = document.getElementById('video-quality');
        vSelect.innerHTML = '<option value="none">No Video (Audio Only)</option>';
        data.video_formats.forEach(f => {
            vSelect.innerHTML += `<option value="${f.id}">${f.label}</option>`;
        });

        const aSelect = document.getElementById('audio-quality');
        aSelect.innerHTML = '';
        data.audio_formats.forEach(f => {
            aSelect.innerHTML += `<option value="${f.id}">${f.label}</option>`;
        });

        const subCheck = document.getElementById('gen-subs');
        const warn = document.getElementById('duration-warning');
        subCheck.checked = false; 
        
        if (data.duration > 7200) {
            subCheck.disabled = true;
            warn.style.display = 'inline';
        } else {
            subCheck.disabled = false;
            warn.style.display = 'none';
        }
        toggleApiKey();
        changeSlide(2);

    } catch (e) {
        alert("Error fetching info: " + e.message);
    } finally {
        btn.innerHTML = 'Next <i class="ph ph-arrow-right"></i>';
    }
}

async function startConversion() {
    const groqKey = document.getElementById('groq-key').value;
    const genSubs = document.getElementById('gen-subs').checked;
    const translateSubs = document.getElementById('translate-subs').checked;

    if (genSubs && !groqKey) return alert("Please enter a Groq API Key to generate subtitles.");
    
    if(groqKey) localStorage.setItem('groqKey', groqKey);

    const payload = {
        url: document.getElementById('youtube-url').value,
        video_quality: document.getElementById('video-quality').value,
        audio_quality: document.getElementById('audio-quality').value,
        groq_api_key: groqKey,
        gen_subtitles: genSubs,
        translate_subs: translateSubs
    };

    // Reset Progress UI
    resetTaskUI();
    changeSlide(3);

    try {
        const res = await fetch('/api/convert', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        monitorProgress(data.job_id);
    } catch(e) {
        alert("Conversion failed to start");
        changeSlide(2);
    }
}

function resetTaskUI() {
    const tasks = ['audio_dl', 'video_dl', 'conversion', 'transcription', 'finalization'];
    tasks.forEach(t => {
        const el = document.getElementById(`task-${t}`);
        el.className = 'task-item'; // remove running/done/skipped
        el.querySelector('.task-detail').textContent = 'Waiting...';
        el.querySelector('.task-icon').innerHTML = '<i class="ph ph-circle"></i>';
        const bar = el.querySelector('.progress-fill');
        if(bar) bar.style.width = '0%';
    });
}

function monitorProgress(jobId) {
    if(eventSource) eventSource.close();
    eventSource = new EventSource(`/api/status/${jobId}`);

    eventSource.onmessage = function(e) {
        const job = JSON.parse(e.data);
        const tasks = job.tasks;

        // Iterate over task keys
        for (const [key, info] of Object.entries(tasks)) {
            const el = document.getElementById(`task-${key}`);
            if(!el) continue;

            const detailEl = el.querySelector('.task-detail');
            const iconEl = el.querySelector('.task-icon');
            const bar = el.querySelector('.progress-fill');

            // Update Text
            if(info.detail) detailEl.textContent = info.detail;

            // Update Progress Bar (if exists)
            if(bar && info.progress) {
                bar.style.width = `${info.progress}%`;
            }

            // Update States
            el.className = `task-item ${info.status}`;
            
            if (info.status === 'running') {
                iconEl.innerHTML = '<i class="ph ph-spinner"></i>';
            } else if (info.status === 'done') {
                iconEl.innerHTML = '<i class="ph ph-check-circle"></i>';
            } else if (info.status === 'skipped') {
                iconEl.innerHTML = '<i class="ph ph-minus-circle"></i>';
                detailEl.textContent = 'Skipped';
            }
        }

        if (job.status === 'completed') {
            eventSource.close();
            // Short delay to let animations finish
            setTimeout(() => showResult(job.result), 500);
        } else if (job.status === 'error') {
            eventSource.close();
            alert("Error: " + job.error);
            changeSlide(2);
        }
    };
}

function showResult(result) {
    document.getElementById('res-thumb').src = currentData.thumbnail;
    document.getElementById('res-title').textContent = result.title;
    document.getElementById('res-size').textContent = result.size;
    document.getElementById('res-duration').textContent = formatDuration(currentData.duration);
    
    const dlBtn = document.getElementById('btn-dl-media');
    dlBtn.href = `/download/${result.filename}`;
    
    const subBtn = document.getElementById('btn-dl-sub');
    if (result.srt_filename) {
        subBtn.style.display = 'flex';
        subBtn.href = `/download/${result.srt_filename}`;
    } else {
        subBtn.style.display = 'none';
    }

    saveHistory({
        title: result.title,
        filename: result.filename,
        srt: result.srt_filename
    });

    changeSlide(4);
}

// History functions remain same as before...
function saveHistory(item) {
    let history = JSON.parse(localStorage.getItem('clipflow_history') || '[]');
    history.unshift(item);
    if(history.length > 5) history.pop();
    localStorage.setItem('clipflow_history', JSON.stringify(history));
    loadHistory();
}

function loadHistory() {
    const history = JSON.parse(localStorage.getItem('clipflow_history') || '[]');
    const list = document.getElementById('history-list');
    list.innerHTML = '';
    
    history.forEach(h => {
        let html = `<li>
            <span>${h.title.substring(0, 30)}...</span>
            <div>
                <a href="/download/${h.filename}" class="history-link">Media</a>`;
        if(h.srt) {
            html += ` | <a href="/download/${h.srt}" class="history-link">Sub</a>`;
        }
        html += `</div></li>`;
        list.innerHTML += html;
    });
}

function resetApp() {
    document.getElementById('youtube-url').value = '';
    changeSlide(1);
    resetTaskUI();
}