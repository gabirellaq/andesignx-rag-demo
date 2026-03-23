import os
import gradio as gr
from chat_logic_deploy import Chatbot
import uuid
from flask import Flask, request, jsonify
import base64

# 初始化后端
print("正在创建 Chatbot 实例...")
chatbot_instance = Chatbot()
print("Chatbot 实例创建成功。")


# 定义核心函数
def _messages_to_pairs(history):
    """
    将 Gradio Chatbot messages 格式转换为 stream_chat 需要的 (user, assistant) pairs。
    Gradio 6 Chatbot messages: [{role: 'user'|'assistant', content: '...'}, ...]
    """
    if not history:
        return []

    # 兼容旧版格式：[[user, assistant], ...]
    if isinstance(history[0], (list, tuple)) and len(history[0]) >= 2:
        pairs = []
        for u, a in history:
            pairs.append((u, "" if a is None else str(a)))
        return pairs

    def _message_content_to_text(content):
        """Gradio Chatbot content 可能是字符串或 [{type:'text', text:'...'}, ...]。这里统一提取文本。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        parts.append(str(item.get("text", "")))
                    elif "text" in item:
                        parts.append(str(item.get("text", "")))
            return "".join(parts).strip()
        return str(content)

    # 新版 messages: dictionaries
    pairs = []
    pending_user = None
    pending = False
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = _message_content_to_text(msg.get("content", ""))
        if role == "user":
            pending_user = content
            pending = True
        elif role == "assistant" and pending:
            pairs.append((pending_user, content or ""))
            pending_user = None
            pending = False

    if pending:
        pairs.append((pending_user, ""))
    return pairs


def _pairs_to_messages(pairs):
    """将 (user, assistant) pairs 转换为 Gradio Chatbot messages 格式。"""
    messages = []
    for u, a in pairs:
        user_text = "" if u is None else str(u)
        assistant_text = "" if a is None else str(a)
        messages.append({"role": "user", "content": [{"type": "text", "text": user_text}]})
        messages.append({"role": "assistant", "content": [{"type": "text", "text": assistant_text}]})
    return messages


def add_user_message(message, history, user_id):
    if not message.strip():
        return gr.update(value=""), history, user_id

    # 如果user_id为空，生成一个新的UUID并创建用户
    if not user_id:
        import uuid
        new_user_id = str(uuid.uuid4())
        # 创建用户记录
        chatbot_instance.create_user(new_user_id)
        # 添加用户消息并返回新的user_id
        pairs = _messages_to_pairs(history)
        pairs.append((message, ""))
        new_history = _pairs_to_messages(pairs)
        return gr.update(value=""), new_history, new_user_id

    # 如果user_id已存在，正常处理消息
    pairs = _messages_to_pairs(history)
    pairs.append((message, ""))
    new_history = _pairs_to_messages(pairs)
    return gr.update(value=""), new_history, user_id


def predict(history, last_question_id, user_id):
    pairs = _messages_to_pairs(history)
    if not pairs:
        yield history, None
        return

    user_message = pairs[-1][0]
    response_generator = chatbot_instance.stream_chat(user_message, pairs[:-1], user_id)

    q_id = None
    for item in response_generator:
        if not isinstance(item, tuple) or len(item) != 2:
            print(f"错误：生成器返回了无效格式的数据: {item}")  # 调试信息
            continue
        answer_chunk, q_id_chunk = item
        pairs[-1] = (user_message, answer_chunk)
        new_history = _pairs_to_messages(pairs)
        if q_id_chunk:
            q_id = q_id_chunk
        yield new_history, q_id


def handle_feedback(feedback_choice, last_id):
    if last_id is None:
        gr.Warning("当前没有可以反馈的问答。")
        return
    feedback_result = chatbot_instance.add_feedback(last_id, feedback_choice.lower())
    gr.Info(feedback_result)


def get_example_questions():
    return [
        "Ant design X是什么？",
        "Ant design X最新的更新版本是什么？",
        "Ant design X如何在 create-react-app 中使用",
        "X Skill的核心优势有哪些？",
        "Ant design X有哪些组件"
    ]

# 自定义CSS样式
custom_css = """
/* 全局样式和字体 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body, .gradio-container { 
    font-family: "Inter", "Helvetica Neue", "Helvetica", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "微软雅黑", "Arial", sans-serif !important; 
    background: linear-gradient(135deg, #f8fbff 0%, #eef3ff 50%, #eaf7f5 100%) !important; /* 更浅更柔和的渐变 */
    min-height: 100vh !important;
    position: relative;
    overflow-x: hidden;
}

/* 动态背景粒子效果 */
body::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-image: 
        radial-gradient(1000px 400px at -10% 20%, rgba(102, 126, 234, 0.08), transparent 60%), /* 左侧柔和装饰 */
        radial-gradient(800px 300px at 110% 70%, rgba(118, 75, 162, 0.08), transparent 60%),   /* 右侧柔和装饰 */
        radial-gradient(600px 250px at 50% -10%, rgba(46, 213, 115, 0.06), transparent 70%);   /* 顶部中央淡淡装饰 */
    animation: float 20s ease-in-out infinite;
    pointer-events: none;
    z-index: -1;
}

@keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    33% { transform: translateY(-20px) rotate(1deg); }
    66% { transform: translateY(10px) rotate(-1deg); }
}

.gradio-container { 
    max-width: 2000px !important; /* 适当加宽，减轻留白 */
    margin: opx 0px 0px 0px !important; 
    padding: 8px 300px 0px 300px !important; /* 稍增内边距，增强呼吸感 */
}

/* 主容器样式 */
.main-container {
    background: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(20px) !important;
    border-radius: 24px !important;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1) !important;
    padding: 40px !important;
    margin: 20px 0 !important;
}

/* 页面头部样式 */
.main-header {
    text-align: center;
    margin-bottom: 0; /* 紧挨着chatbox */
    padding: 8px 0; /* 更紧凑 */
    background: linear-gradient(135deg, #e4ecff 0%, #eae6ff 50%, #e8f8f2 100%); /* 浅色系与整体背景协调 */
    border-radius: 20px;
    color: white;
    position: relative;
    overflow: hidden;
}

.main-header::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="rgba(255,255,255,0.1)"/><circle cx="75" cy="75" r="1" fill="rgba(255,255,255,0.1)"/><circle cx="50" cy="10" r="0.5" fill="rgba(255,255,255,0.1)"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
    opacity: 0.3;
}

.main-header h1 {
    color: #334155; /* 深灰可读性更好 */
    font-size: 3rem;
    font-weight: 700;
    margin-bottom: 15px;
    text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    position: relative;
    z-index: 1;
}

.main-header p {
    color: #475569; /* 次要深灰 */
    font-size: 1.2rem;
    font-weight: 300;
    position: relative;
    z-index: 1;
}

/* 聊天容器样式 */
.chat-container {
    display: flex;
    flex-direction: column;
    height: 100vh; /* 提升整体高度 */
    border-radius: 22px;
    box-shadow: 0 12px 36px rgba(15, 23, 42, 0.08);
    overflow: hidden;
    background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
    border: 1px solid rgba(255,255,255,0.2);
}

.chatbot {
    flex-grow: 1;
    overflow-y: auto;
    background: linear-gradient(180deg, #f7faff 0%, #ffffff 100%); /* 更浅 */
    padding: 20px;
    scrollbar-width: thin;
    scrollbar-color: #c1c1c1 #f1f1f1;
}

.chatbot::-webkit-scrollbar {
    width: 8px;
}

.chatbot::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
}

.chatbot::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 4px;
}

.chatbot::-webkit-scrollbar-thumb:hover {
    background: #a8a8a8;
}

/* 输入区域样式 */
.input-area {
    padding: 25px;
    background: linear-gradient(135deg, #f9fbff 0%, #ffffff 100%);
    border-top: 1px solid rgba(0,0,0,0.1);
    position: relative;
}

.input-area::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.3), transparent);
}

/* 反馈按钮区域样式 */
.feedback-area {
    margin-bottom: 20px;
    display: flex;
    justify-content: center;
    gap: 15px;
    flex-wrap: wrap;
}

.feedback-area button {
    border-radius: 22px;
    padding: 12px 20px;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: 2px solid transparent;
    position: relative;
    overflow: hidden;
    background: linear-gradient(135deg, #f2f6ff 0%, #eef4ff 100%) !important; /* 更浅 */
    color: #495057 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
}

.feedback-area button::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.2), transparent);
    transition: left 0.5s;
}

.feedback-area button:hover::before {
    left: 100%;
}

.feedback-area button:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}

/* 特殊按钮样式 */
.feedback-area button[data-testid*="feedback"] {
    background: linear-gradient(135deg, #f2f6ff 0%, #eef4ff 100%) !important;
    color: #495057 !important;
}

.feedback-area button[data-testid*="feedback"]:hover {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}

.feedback-area button[data-testid*="clear"] {
    background: linear-gradient(135deg, #f2f6ff 0%, #eef4ff 100%) !important;
    color: #495057 !important;
}

.feedback-area button[data-testid*="clear"]:hover {
    background: linear-gradient(135deg, #dc3545 0%, #fd7e14 100%) !important;
    color: white !important;
}

/* 输入框和发送按钮样式 */
.input-row {
    display: flex;
    gap: 15px;
    align-items: center;
}

.input-row .textbox {
    border-radius: 25px !important;
    border: 2px solid rgba(102, 126, 234, 0.2) !important;
    padding: 15px 20px !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
    box-shadow: none !important;
}

.input-row .textbox:focus {
    border-color: #667eea !important;
    box-shadow: none !important;
    transform: translateY(-1px) !important;
}

.input-row button {
    border-radius: 25px !important;
    padding: 15px 25px !important;
    font-weight: 600 !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    position: relative;
    overflow: hidden;
}

.input-row button::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
    transition: left 0.5s;
}

.input-row button:hover::before {
    left: 100%;
}

.input-row button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4) !important;
}

/* 示例问题区域样式 */
.example-area {
    margin-top: 30px;
    padding: 24px;
    background: linear-gradient(135deg, #f7faff 0%, #ffffff 100%);
    border-radius: 18px;
    border: 1px solid rgba(30, 64, 175, 0.06);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

/* 已集成文档区域样式 */
.docs-area {
    margin-top: 16px;
    padding: 20px;
    background: linear-gradient(135deg, #f0f8ff 0%, #ffffff 100%);
    border-radius: 16px;
    border: 1px solid rgba(30, 64, 175, 0.08);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.docs-area h3 {
    margin-top: 0;
    color: #2c3e50;
    font-size: 1.2rem;
    font-weight: 600;
    margin-bottom: 6px;
    text-align: center;
}

.docs-area p {
    text-align: center;
    color: #64748b;
    margin: 0 0 12px 0;
    font-size: 0.95rem;
}

.doc-btn {
    border-radius: 14px !important;
    padding: 12px 18px !important;
    background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%) !important;
    color: #475569 !important;
    border: 2px solid rgba(102, 126, 234, 0.1) !important;
    font-weight: 500 !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
    text-decoration: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin-bottom: 10px !important;
}

.doc-btn:hover {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3) !important;
    border-color: rgba(102, 126, 234, 0.3) !important;
}

.example-area h3 {
    margin-top: 0;
    color: #2c3e50;
    font-size: 1.3rem;
    font-weight: 600;
    margin-bottom: 20px;
    text-align: center;
}

.example-btn {
    margin: 8px !important;
    border-radius: 20px !important;
    padding: 10px 20px !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: none !important;
    font-weight: 500 !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 2px 10px rgba(102, 126, 234, 0.3) !important;
}

.example-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4) !important;
}

/* 页脚样式 */
.footer {
    text-align: center;
    margin-top: 40px;
    color: #475569;
    font-size: 0.95rem;
    padding: 20px;
    background: linear-gradient(135deg, rgba(241, 245, 249, 0.8), rgba(236, 252, 244, 0.8));
    border-radius: 12px;
    backdrop-filter: blur(10px);
}

/* 聊天气泡样式优化 */
.chatbot .message {
    padding: 0 !important;
    margin: 15px 0 !important;
    border-radius: 0 !important;
    background: none !important;
    box-shadow: none !important;
    border: none !important;
    animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.chatbot .message-row {
    margin: 0 !important;
}

/* 用户消息样式 - 右侧显示 */
.chatbot .message .user {
    background: transparent !important; /* 透明背景 */
    color: #334155 !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    margin: 0 0 0 auto !important;
    max-width: 75% !important;
    position: relative;
    animation: slideInRight 0.5s ease-out;
    text-align: right !important;
}

/* AI回复样式 - 左侧显示 */
.chatbot .message .bot {
    background: white !important;
    color: #2c3e50 !important;
    border-radius: 20px 20px 20px 5px !important;
    padding: 15px 20px !important;
    margin: 0 auto 0 0 !important;
    max-width: 75% !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;
    border: 1px solid rgba(0,0,0,0.05) !important;
    position: relative;
    animation: slideInLeft 0.5s ease-out;
    text-align: left !important;
}


/* 用户长消息可折叠样式 */
.chatbot .message.user .wrap.collapsible {
    display: -webkit-box !important;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    position: relative;
}
.chatbot .message.user .wrap.collapsible::after {
    content: "";
    position: absolute;
    bottom: 0; right: 0; left: 0;
    height: 2.2em;
    background: linear-gradient(180deg, rgba(255,255,255,0), rgba(255,255,255,1));
    pointer-events: none;
}
.chatbot .message.user .wrap.collapsible.expanded {
    -webkit-line-clamp: unset;
    overflow: visible;
}
.chatbot .message.user .wrap.collapsible.expanded::after {
    display: none;
}
.chatbot .message.user .md-toggle {
    display: inline-block;
    margin-top: 6px;
    color: #667eea;
    cursor: pointer;
    font-size: 12px;
}

@keyframes slideInRight {
    from {
        opacity: 0;
        transform: translateX(30px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

@keyframes slideInLeft {
    from {
        opacity: 0;
        transform: translateX(-30px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

/* 移除可能导致问题的伪元素 */
.chatbot .message::before,
.chatbot .message::after {
    display: none !important;
}

.chatbot .message .md {
    padding: 0 !important;
    margin: 0 !important;
    line-height: 1.6 !important;
}

/* 确保聊天气泡布局正确 */
.chatbot .message {
    display: flex !important;
    flex-direction: column !important;
}

.chatbot .message .user {
    align-self: flex-end !important;
}

.chatbot .message .bot {
    align-self: flex-start !important;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .gradio-container {
        padding: 10px !important;
    }

    .main-container {
        padding: 20px !important;
        margin: 10px 0 !important;
    }

    .main-header h1 {
        font-size: 2rem !important;
    }

    .chat-container {
        height: 60vh !important;
    }

    .feedback-area {
        flex-direction: column !important;
        align-items: center !important;
    }

    .input-row {
        flex-direction: column !important;
    }

    .input-row .textbox {
        width: 100% !important;
    }
}

/* 加载动画 */
.loading {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid rgba(102, 126, 234, 0.3);
    border-radius: 50%;
    border-top-color: #667eea;
    animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* 欢迎消息样式 */
.welcome-message {
    text-align: center;
    padding: 30px;
    background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    border-radius: 20px;
    margin-bottom: 20px;
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    position: relative;
    overflow: hidden;
}

.welcome-message::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(102, 126, 234, 0.1), transparent);
    animation: shimmer 3s infinite;
}

@keyframes shimmer {
    0% { left: -100%; }
    100% { left: 100%; }
}

.welcome-message .emoji {
    font-size: 2rem;
    margin: 0 10px;
    animation: bounce 2s infinite;
    display: inline-block;
}

@keyframes bounce {
    0%, 20%, 50%, 80%, 100% {
        transform: translateY(0);
    }
    40% {
        transform: translateY(-10px);
    }
    60% {
        transform: translateY(-5px);
    }
}

/* 状态指示器和加载效果 */
.status-indicator {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #28a745;
    margin-right: 8px;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(1.2); }
    100% { opacity: 1; transform: scale(1); }
}

/* 输入框焦点效果增强 */
.input-row .textbox:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
    transform: translateY(-1px) !important;
    background: white !important;
}

/* 按钮点击效果 */
.feedback-area button:active,
.input-row button:active {
    transform: translateY(1px) !important;
    transition: transform 0.1s ease !important;
}

/* 滚动条美化 */
.chatbot::-webkit-scrollbar {
    width: 10px;
}

.chatbot::-webkit-scrollbar-track {
    background: rgba(0,0,0,0.05);
    border-radius: 5px;
}

.chatbot::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 5px;
    border: 2px solid rgba(255,255,255,0.8);
}

.chatbot::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
}
"""


def image_to_base64(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return ""

# 构建Gradio UI
with gr.Blocks(theme=gr.themes.Soft(), css=custom_css, title="Ant design X AI文档助手(Beta)") as demo:
    # 添加用户ID状态 - 简单创建，不添加额外参数
    user_id = gr.State("")
    last_question_id = gr.State(None)

    logo_url = ""  # 本地文件路径
    base64_image = image_to_base64(logo_url)
    logo_img = f'<img src="data:image/jpeg;base64,{base64_image}" alt="logo" style="height: 70px; margin-right: -20px; margin-top: 6px;">' if base64_image else ""

    with gr.Column(elem_classes="main-header"):
        gr.HTML(f"""
            <div style="display: flex; align-items: center; justify-content: center; flex-direction: row; position: relative;">
                <div style="display: flex; align-items: center;">
                    {logo_img}
                    <h1 style="font-size:50px; color:#000000;">Ant design X Copilot</h1>
                </div>
                <div style="font-size: 20px; color: #475569; margin-left: 15px;"> (beta)</div>
            </div>
            """)
        # 聊天主区域
    with gr.Column(elem_classes="chat-container"):
        chatbot = gr.Chatbot(
            elem_classes="chatbot",
            value=[],
            height=640
        )

        # 输入区域
        with gr.Column(elem_classes="input-area"):
            with gr.Row(elem_classes="input-row"):
                msg_textbox = gr.Textbox(
                    placeholder="💭 输入您的问题，按Enter发送...",
                    container=False,
                    scale=4,
                    show_label=False,
                    elem_classes="textbox"
                )
                submit_btn = gr.Button("🚀 发送", variant="primary", scale=1)
            # 反馈按钮区域
            with gr.Row(elem_classes="feedback-area"):
                correct_btn = gr.Button("👍 回答有帮助", variant="secondary", elem_classes="feedback-btn")
                incorrect_btn = gr.Button("👎 回答无帮助", variant="secondary", elem_classes="feedback-btn")
                clear_btn = gr.Button("🗑️ 清空对话", variant="secondary", elem_classes="feedback-btn")


    # 示例问题区域
    with gr.Column(elem_classes="example-area"):
        gr.Markdown("### 💡 常见问题示例")
        examples = gr.Examples(
            examples=[[q] for q in get_example_questions()],
            inputs=[msg_textbox],
            label="点击以下问题快速开始",
            examples_per_page=5
        )

    # 添加 Gradio JavaScript API 初始化
    gradio_js = """
    <script>
        // 扩展 Gradio 配置以支持状态操作
        window.addEventListener('load', function() {
            if (window.gradio_config) {
                // 添加设置状态的方法
                window.gradio_config.set_state = function(componentId, value) {
                    const component = window.gradio_config.components.find(c => c.id === componentId);
                    if (component) {
                        component.value = value;
                        // 更新对应的 textarea
                        const textarea = document.querySelector(`#${componentId} textarea`);
                        if (textarea) {
                            textarea.value = value;
                        }
                    }
                };

                // 添加获取状态的方法
                window.gradio_config.get_state = function(componentId) {
                    const component = window.gradio_config.components.find(c => c.id === componentId);
                    return component ? component.value : null;
                };
            }
        });
    </script>
    """
    gr.HTML(gradio_js)

    # 添加自定义HTML和JavaScript用于用户管理
    custom_html = """
    <script>
        function generateUUID() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                const r = Math.random() * 16 | 0;
                const v = c == 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        }

        // 页面加载时生成用户ID并创建用户记录
        document.addEventListener("DOMContentLoaded", function() {
            console.log(Ant design X AI文档助手已加载)

        // 页面关闭时更新用户退出时间
        window.addEventListener("beforeunload", function() {
            // 尝试获取用户ID
            let userId = null;

            // 使用 Gradio 的 JavaScript API 获取状态值
            if (window.gradio_config && window.gradio_config.components) {
                const stateComponents = window.gradio_config.components.filter(
                    component => component.type === 'state'
                );

                if (stateComponents.length >= 1) {
                    const userIdComponent = stateComponents[0];
                    userId = window.gradio_config.get_state(userIdComponent.id);
                }
            }

            if (userId) {
                navigator.sendBeacon('/update_user_exit', JSON.stringify({
                    user_id: userId
                }));
            }
        });
    </script>
    """
    gr.HTML(custom_html)

    # 可折叠长消息的脚本
    collapse_js = """
    <script>
      function enhanceUserMessages() {
        const chat = document.querySelector('.chatbot');
        if (!chat) return;
        const userBubbles = chat.querySelectorAll('.message .user .md');
        userBubbles.forEach(md => {
          if (md.dataset.enhanced === '1') return;
          md.dataset.enhanced = '1';
          // 计算内容高度，超过约3行则折叠
          const clone = md.cloneNode(true);
          clone.style.visibility = 'hidden';
          clone.style.position = 'absolute';
          clone.style.height = 'auto';
          clone.style.webkitLineClamp = 'unset';
          document.body.appendChild(clone);
          const tooTall = clone.scrollHeight > 72; // 约三行
          document.body.removeChild(clone);
          if (tooTall) {
            md.classList.add('collapsible');
            const toggle = document.createElement('span');
            toggle.className = 'md-toggle';
            toggle.textContent = '展开';
            toggle.addEventListener('click', () => {
              const expanded = md.classList.toggle('expanded');
              toggle.textContent = expanded ? '收起' : '展开';
            });
            md.parentElement.appendChild(toggle);
          }
        });
      }

      const observer = new MutationObserver(() => {
        enhanceUserMessages();
      });

      window.addEventListener('load', () => {
        const chatRoot = document.querySelector('.chatbot');
        if (chatRoot) observer.observe(chatRoot, { childList: true, subtree: true });
        enhanceUserMessages();
      });
    </script>
    """
    gr.HTML(collapse_js)

    # 修改事件绑定，添加用户ID参数
    msg_textbox.submit(
        fn=add_user_message,
        inputs=[msg_textbox, chatbot, user_id],
        outputs=[msg_textbox, chatbot, user_id],
        queue=False
    ).then(
        fn=predict,
        inputs=[chatbot, last_question_id, user_id],
        outputs=[chatbot, last_question_id]
    )

    submit_btn.click(
        fn=add_user_message,
        inputs=[msg_textbox, chatbot, user_id],
        outputs=[msg_textbox, chatbot, user_id],
        queue=False
    ).then(
        fn=predict,
        inputs=[chatbot, last_question_id, user_id],
        outputs=[chatbot, last_question_id]
    )

    correct_btn.click(
        fn=handle_feedback,
        inputs=[gr.Textbox("correct", visible=False), last_question_id],
        outputs=None,
    )

    incorrect_btn.click(
        fn=handle_feedback,
        inputs=[gr.Textbox("incorrect", visible=False), last_question_id],
        outputs=None
    )

    clear_btn.click(
        fn=lambda: [None, []],
        outputs=[last_question_id, chatbot]
    )

# 添加Flask路由处理用户管理
app = demo.app


@app.route('/create_user', methods=['POST'])
def create_user():
    print("=== CREATE USER ROUTE CALLED ===")
    data = request.json
    print("Request data:", data)
    user_id = data.get('user_id')
    if user_id:
        result = chatbot_instance.create_user(user_id)
        print(f"User creation result: {result}")
        return jsonify({"status": "success", "user_id": user_id})
    print("Missing user_id in request")
    return jsonify({"status": "error", "message": "Missing user_id"}), 400


@app.route('/update_user_exit', methods=['POST'])
def update_user_exit():
    print("=== UPDATE USER EXIT ROUTE CALLED ===")
    data = request.json
    print("Request data:", data)
    user_id = data.get('user_id')
    if user_id:
        chatbot_instance.update_user_exit(user_id)
        return jsonify({"status": "success"})
    print("Missing user_id in request")
    return jsonify({"status": "error", "message": "Missing user_id"}), 400


# 启动应用
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", 1234)),
        share=False
    )