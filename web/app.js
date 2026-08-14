/**
 * Liebchen — Voice-Activated AI Assistant
 * Client-side logic: wake word detection, speech recognition, chat, and UI control.
 */

// ═══════════════════════════════════════════════════════════════════════════════
//  Configuration
// ═══════════════════════════════════════════════════════════════════════════════
const API_BASE = window.location.origin;
const WAKE_PHRASE = 'jarvis';
const WAKE_PHRASES = ['jarvis', 'hey jarvis', 'jarv', 'hey jarv'];

// ═══════════════════════════════════════════════════════════════════════════════
//  DOM References
// ═══════════════════════════════════════════════════════════════════════════════
const $wakeListener = document.getElementById('wake-listener');
const $panel = document.getElementById('assistant-panel');
const $chatArea = document.getElementById('chat-area');
const $welcomeMsg = document.getElementById('welcome-msg');
const $msgInput = document.getElementById('msg-input');
const $btnSend = document.getElementById('btn-send');
const $btnMic = document.getElementById('btn-mic');
const $btnClose = document.getElementById('btn-close');
const $btnNewChat = document.getElementById('btn-new-chat');
const $btnStopThinking = document.getElementById('btn-stop-thinking');
const $statusBadge = document.getElementById('status-badge');
const $statusText = document.getElementById('status-text');
const $waveformContainer = document.getElementById('waveform-container');
const $listeningLabel = document.getElementById('listening-label');
const $brainOrb = document.getElementById('brain-orb');
const $toastContainer = document.getElementById('toast-container');

// ═══════════════════════════════════════════════════════════════════════════════
//  State
// ═══════════════════════════════════════════════════════════════════════════════
let isOpen = false;
let isSending = false;
let isRecording = false;
let wakeRecognition = null;
let chatRecognition = null;
let threadId = Date.now().toString();
let currentAbortController = null;
let hasMessages = false;
let _wakeOnCooldown = false;
const WAKE_COOLDOWN_MS = 3000; // 3-second cooldown between activations

// ═══════════════════════════════════════════════════════════════════════════════
//  Toast Notifications
// ═══════════════════════════════════════════════════════════════════════════════
function showToast(message, type = 'info', duration = 3500) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    $toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Panel Open / Close
// ═══════════════════════════════════════════════════════════════════════════════
function openPanel() {
    if (isOpen) return;
    isOpen = true;
    $panel.classList.remove('hidden');
    $wakeListener.style.display = 'none';
    stopWakeWordListener();
    $msgInput.focus();
}

function closePanel() {
    if (!isOpen) return;
    isOpen = false;
    $panel.classList.add('hidden');
    $wakeListener.style.display = 'flex';
    stopChatRecognition();
    hideWaveform();
    startWakeWordListener();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Status Management
// ═══════════════════════════════════════════════════════════════════════════════
function setStatus(text, type = '') {
    $statusText.textContent = text;
    $statusBadge.className = `status-badge ${type}`;
    if ($btnStopThinking) {
        if (text === 'Thinking' || type === 'thinking') {
            $btnStopThinking.classList.remove('hidden');
        } else {
            $btnStopThinking.classList.add('hidden');
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Chat API
// ═══════════════════════════════════════════════════════════════════════════════
async function sendMessage(text) {
    if (!text.trim() || isSending) return;

    isSending = true;
    setStatus('Thinking...', 'thinking');
    $btnSend.disabled = true;
    $msgInput.disabled = true;

    // Hide welcome message
    if ($welcomeMsg) {
        $welcomeMsg.style.display = 'none';
        hasMessages = true;
    }

    // Add user message
    appendMessage(text, 'user');

    // Show typing indicator
    const typingEl = showTypingIndicator();

    // Clear input
    $msgInput.value = '';
    autoResize($msgInput);

    if (currentAbortController) {
        currentAbortController.abort();
    }
    currentAbortController = new AbortController();

    try {
        const res = await fetch(`${API_BASE}/api/chat_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, thread_id: threadId }),
            signal: currentAbortController.signal
        });

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        // Create empty AI message bubble for streaming
        typingEl.remove();
        
        const msg = document.createElement('div');
        msg.className = 'message ai';
        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = '🧠';
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble';
        msg.appendChild(avatar);
        msg.appendChild(bubble);
        $chatArea.appendChild(msg);
        $chatArea.scrollTop = $chatArea.scrollHeight;

        // Read Server-Sent Events stream
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = "";
        let buffer = "";
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            let lines = buffer.split('\n');
            // The last element is either an empty string (if buffer ended with \n)
            // or an incomplete line. Keep it in the buffer.
            buffer = lines.pop();
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    if (dataStr.trim()) {
                        try {
                            const parsed = JSON.parse(dataStr);
                            if (parsed.error) throw new Error(parsed.error);
                            if (parsed.thread_id) threadId = parsed.thread_id;
                            if (parsed.chunk) {
                                fullResponse += parsed.chunk;
                                bubble.innerHTML = formatMarkdown(fullResponse);
                                $chatArea.scrollTop = $chatArea.scrollHeight;
                            }
                        } catch(e) {
                            console.error("SSE parse error", e, dataStr);
                        }
                    }
                }
            }
        }

        setStatus('Ready');
        // Speak the response (optional, first 300 chars)
        speak(fullResponse.slice(0, 300));

    } catch (err) {
        typingEl.remove();
        if (err.name === 'AbortError') {
            appendMessage(`⚠️ Stopped thinking.`, 'ai');
            setStatus('Ready');
        } else {
            appendMessage(`⚠️ Error: ${err.message}`, 'ai');
            setStatus('Error', 'error');
            showToast(`Failed to get response: ${err.message}`, 'error');
        }
    } finally {
        currentAbortController = null;
        isSending = false;
        $btnSend.disabled = !$msgInput.value.trim();
        $msgInput.disabled = false;
        $msgInput.focus();
    }
}

function stopThinking() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
    setStatus('Ready');
    if ($btnStopThinking) $btnStopThinking.classList.add('hidden');
    showToast('⏹️ Stopped thinking. Listening...', 'info', 2000);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Message Rendering
// ═══════════════════════════════════════════════════════════════════════════════
function appendMessage(text, sender) {
    const msg = document.createElement('div');
    msg.className = `message ${sender}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = sender === 'ai' ? '🧠' : '👤';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = formatMarkdown(text);

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    $chatArea.appendChild(msg);
    scrollToBottom();
}

function formatMarkdown(text) {
    // Basic markdown rendering
    return text
        // Code blocks
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        // Headers
        .replace(/^### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        // List items
        .replace(/^- (.+)$/gm, '• $1')
        // Line breaks
        .replace(/\n/g, '<br>');
}

function showTypingIndicator() {
    const msg = document.createElement('div');
    msg.className = 'message ai';
    msg.id = 'typing-msg';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = '🧠';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble typing-indicator';
    bubble.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    $chatArea.appendChild(msg);
    scrollToBottom();
    return msg;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        $chatArea.scrollTop = $chatArea.scrollHeight;
    });
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Text-to-Speech
// ═══════════════════════════════════════════════════════════════════════════════
function speak(text) {
    if (!('speechSynthesis' in window)) return;
    // Clean markdown artifacts
    const clean = text.replace(/[#*_`]/g, '').replace(/<[^>]+>/g, '');
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 0.8;
    speechSynthesis.speak(utterance);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Wake Word Detection (Continuous Listening)
// ═══════════════════════════════════════════════════════════════════════════════
function startWakeWordListener() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        console.warn('Speech recognition not supported');
        $wakeListener.querySelector('.wake-label').innerHTML = 'Click to activate <strong>Liebchen</strong>';
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    wakeRecognition = new SpeechRecognition();
    wakeRecognition.continuous = true;
    // Only process final results to avoid duplicate triggers from interim transcripts
    wakeRecognition.interimResults = false;
    wakeRecognition.lang = 'en-US';

    wakeRecognition.onresult = (event) => {
        // Skip if we're already on cooldown (prevents rapid-fire activations)
        if (_wakeOnCooldown) return;

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.toLowerCase().trim();
            console.log('[Wake] Heard:', transcript);

            const detected = WAKE_PHRASES.some(phrase => transcript.includes(phrase));
            if (detected) {
                console.log('[Wake] ✅ Wake word detected!');

                // Engage cooldown — ignore all further detections for 3 seconds
                _wakeOnCooldown = true;
                setTimeout(() => { _wakeOnCooldown = false; }, WAKE_COOLDOWN_MS);

                showToast('🧠 Jarvis is activated. I\'m listening.', 'success', 3000);
                speak("Jarvis is activated. I'm listening.");
                openPanel();
                
                // Automatically start listening right after waking up
                setTimeout(() => {
                    if (!isRecording) {
                        startChatRecognition();
                    }
                }, 400); // small delay to allow panel animation to start
                
                return;
            }
        }
    };

    wakeRecognition.onend = () => {
        // Restart if panel is not open
        if (!isOpen && wakeRecognition) {
            try {
                wakeRecognition.start();
            } catch (e) {
                // Already started
            }
        }
    };

    wakeRecognition.onerror = (e) => {
        if (e.error === 'no-speech' || e.error === 'aborted') return;
        console.warn('[Wake] Error:', e.error);
    };

    try {
        wakeRecognition.start();
        $wakeListener.classList.add('listening');
        console.log('[Wake] Listening for wake word...');
    } catch (e) {
        console.warn('[Wake] Could not start:', e);
    }
}

function stopWakeWordListener() {
    if (wakeRecognition) {
        try {
            wakeRecognition.abort();
        } catch (e) {}
        wakeRecognition = null;
    }
    $wakeListener.classList.remove('listening');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Chat Voice Input (Push-to-talk style)
// ═══════════════════════════════════════════════════════════════════════════════
function toggleChatRecognition() {
    if (isRecording) {
        stopChatRecognition();
    } else {
        startChatRecognition();
    }
}

function startChatRecognition() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        showToast('Speech recognition not supported in this browser', 'error');
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    chatRecognition = new SpeechRecognition();
    chatRecognition.continuous = true;
    chatRecognition.interimResults = true;
    chatRecognition.lang = 'en-US';

    isRecording = true;
    $btnMic.classList.add('recording');
    showWaveform('Listening...');

    let silenceTimer = null;

    chatRecognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = 0; i < event.results.length; i++) {
            const t = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += t + ' ';
            } else {
                interimTranscript += t;
            }
        }

        const fullText = (finalTranscript + interimTranscript).trim();
        $msgInput.value = fullText;
        $btnSend.disabled = !fullText;
        $listeningLabel.textContent = interimTranscript ? 'Hearing you...' : 'Listening...';

        // Reset silence timer — wait 2.0 seconds of silence before finalizing & sending
        clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
            if (isRecording && fullText) {
                stopChatRecognition();
            }
        }, 2000);
    };

    chatRecognition.onend = () => {
        if (silenceTimer) clearTimeout(silenceTimer);
        isRecording = false;
        $btnMic.classList.remove('recording');
        hideWaveform();

        // Auto-send if we got text
        const text = $msgInput.value.trim();
        if (text) {
            sendMessage(text);
        }
    };

    chatRecognition.onerror = (e) => {
        console.warn('[Chat] Speech error:', e.error);
        isRecording = false;
        $btnMic.classList.remove('recording');
        hideWaveform();
        if (e.error !== 'no-speech') {
            showToast(`Mic error: ${e.error}`, 'error');
        }
    };

    try {
        chatRecognition.start();
    } catch (e) {
        showToast('Could not start microphone', 'error');
        isRecording = false;
        $btnMic.classList.remove('recording');
        hideWaveform();
    }
}

function stopChatRecognition() {
    if (chatRecognition) {
        try {
            chatRecognition.stop();
        } catch (e) {}
        chatRecognition = null;
    }
    isRecording = false;
    $btnMic.classList.remove('recording');
    hideWaveform();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Waveform Control
// ═══════════════════════════════════════════════════════════════════════════════
function showWaveform(label = 'Listening...') {
    $waveformContainer.classList.add('active');
    $listeningLabel.textContent = label;
}

function hideWaveform() {
    $waveformContainer.classList.remove('active');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Auto-resize Textarea
// ═══════════════════════════════════════════════════════════════════════════════
function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ═══════════════════════════════════════════════════════════════════════════════
//  New Thread
// ═══════════════════════════════════════════════════════════════════════════════
async function startNewThread() {
    try {
        const res = await fetch(`${API_BASE}/api/new-thread`, { method: 'POST' });
        const data = await res.json();
        threadId = data.thread_id;

        // Clear chat
        $chatArea.innerHTML = '';
        $chatArea.appendChild(createWelcome());
        hasMessages = false;

        showToast('New conversation started', 'success', 2000);
    } catch (e) {
        showToast('Failed to create new thread', 'error');
    }
}

function createWelcome() {
    const div = document.createElement('div');
    div.className = 'welcome-message';
    div.id = 'welcome-msg';
    div.innerHTML = `
        <div class="welcome-icon">🧠</div>
        <h2>Hello, I'm Jarvis</h2>
        <p>Your personal AI assistant. Ask me anything — type below or click the mic to speak.</p>
        <div class="quick-actions">
            <button class="quick-btn" data-msg="What are my pending tasks?">📋 My Tasks</button>
            <button class="quick-btn" data-msg="Show me my schedule">📅 Schedule</button>
            <button class="quick-btn" data-msg="Analyze my skills">📊 Skill Analysis</button>
            <button class="quick-btn" data-msg="Create a study plan for this week">📚 Study Plan</button>
        </div>
    `;
    // Re-bind quick buttons
    div.querySelectorAll('.quick-btn').forEach(btn => {
        btn.addEventListener('click', () => sendMessage(btn.dataset.msg));
    });
    return div;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Event Listeners
// ═══════════════════════════════════════════════════════════════════════════════
function init() {
    // Open panel on wake listener click
    $wakeListener.addEventListener('click', () => {
        openPanel();
    });

    // Close panel
    $btnClose.addEventListener('click', closePanel);

    // Stop thinking
    $btnStopThinking?.addEventListener('click', stopThinking);

    // Close on backdrop click (but not when clicking inside the panel content)
    document.querySelector('.panel-backdrop')?.addEventListener('click', closePanel);
    document.querySelector('.panel-content')?.addEventListener('click', (e) => e.stopPropagation());

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && isOpen) closePanel();
    });

    // New chat
    $btnNewChat.addEventListener('click', startNewThread);
    
    // Power button (Quit Application)
    document.getElementById('btn-power')?.addEventListener('click', () => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.quit();
        } else {
            showToast('Cannot quit in web-only mode', 'error');
        }
    });

    // Send on Enter
    $msgInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if ($msgInput.value.trim()) {
                sendMessage($msgInput.value.trim());
            }
        }
    });

    // Enable/disable send button
    $msgInput.addEventListener('input', () => {
        $btnSend.disabled = !$msgInput.value.trim();
        autoResize($msgInput);
    });

    // Send button click
    $btnSend.addEventListener('click', () => {
        if ($msgInput.value.trim()) {
            sendMessage($msgInput.value.trim());
        }
    });

    // Mic button
    $btnMic.addEventListener('click', toggleChatRecognition);

    // Quick action buttons
    document.querySelectorAll('.quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            sendMessage(btn.dataset.msg);
        });
    });

    // Start wake word listener
    startWakeWordListener();

    // Health check
    checkHealth();
}

async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        if (data.status === 'ok') {
            console.log('✅ Liebchen API healthy');
            if (data.user) {
                showToast(`Welcome back, ${data.user}! 🧠`, 'success', 3000);
            }
        }
    } catch (e) {
        showToast('⚠️ Cannot connect to Liebchen API. Is the server running?', 'error', 5000);
        setStatus('Disconnected', 'error');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', init);
