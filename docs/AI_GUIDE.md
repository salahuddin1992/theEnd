# 🤖 دليل الذكاء الاصطناعي الموزع - Distributed AI Guide

## نظرة عامة - Overview

يوفر نظام theEnd منصة متكاملة للذكاء الاصطناعي الشخصي الموزع، تتيح لك:

- 💬 **محادثة ذكية** مع نماذج LLM محلية
- 🤖 **وكلاء أذكياء** لتنفيذ المهام تلقائياً
- ⚡ **استنتاج موزع** عبر عدة حواسيب
- 📦 **إدارة النماذج** مركزية

## المتطلبات - Requirements

```bash
# تثبيت Ollama (لتشغيل النماذج محلياً)
curl -fsSL https://ollama.com/install.sh | sh

# تحميل نموذج
ollama pull llama3.2
```

## البدء السريع - Quick Start

### 1. المحادثة التفاعلية

```bash
# بدء محادثة
dc-ai chat start

# أو مع نموذج محدد
dc-ai chat start --model mistral
```

### 2. إرسال رسالة واحدة

```bash
dc-ai chat send "ما هو Python؟"
```

### 3. تشغيل وكيل

```bash
# وكيل عام
dc-ai agent run "ابحث عن ملفات Python في المشروع"

# وكيل برمجة
dc-ai agent run --type coder "اكتب دالة لحساب المضروب"
```

## المكونات الرئيسية - Main Components

### 1. موفرو LLM (LLM Providers)

يدعم النظام عدة backends:

| Provider | الوصف | URL الافتراضي |
|----------|-------|--------------|
| Ollama | تشغيل محلي | `http://localhost:11434` |
| vLLM | خدمة عالية الأداء | `http://localhost:8000` |
| OpenAI | API خارجي | `https://api.openai.com` |

```python
from distributed_cluster.ai.llm import OllamaProvider

# إنشاء موفر
provider = OllamaProvider()

# توليد نص
response = await provider.generate(
    prompt="Hello, how are you?",
    model="llama3.2",
)
print(response.text)
```

### 2. نظام الوكلاء (Agents)

```python
from distributed_cluster.ai.agents import Agent, AgentTask
from distributed_cluster.ai.agents.tools import get_default_tools

# إنشاء وكيل
agent = Agent(
    name="assistant",
    llm_provider=provider,
    model="llama3.2",
    tools=get_default_tools(),
)

# تنفيذ مهمة
result = await agent.run("Find all Python files and count lines")
print(result.result)
```

#### الأدوات المتاحة للوكلاء

| Tool | الوصف |
|------|-------|
| `shell` | تنفيذ أوامر Shell |
| `file` | قراءة وكتابة الملفات |
| `web_search` | البحث في الويب |
| `web_fetch` | جلب محتوى URL |
| `python` | تنفيذ كود Python |
| `calculator` | حسابات رياضية |
| `memory` | تخزين واسترجاع البيانات |

### 3. نظام المحادثة (Chat)

```python
from distributed_cluster.ai.chat import ConversationManager

# إنشاء مدير محادثات
manager = ConversationManager(
    llm_provider=provider,
    default_model="llama3.2",
)

# إنشاء محادثة
conv = manager.create_conversation(
    system_prompt="You are a helpful assistant.",
)

# إرسال رسالة
response = await manager.chat(conv, "مرحبا!")
print(response.content)

# محادثة مع streaming
async for chunk in manager.chat_stream(conv, "اكتب قصة قصيرة"):
    print(chunk, end="")
```

### 4. الاستنتاج الموزع (Distributed Inference)

```python
from distributed_cluster.ai.inference import InferenceRouter

# إنشاء موجه
router = InferenceRouter(strategy="round_robin")

# إضافة عقد
await router.add_node(url="http://server1:11434", provider_type="ollama")
await router.add_node(url="http://server2:11434", provider_type="ollama")

# بدء الموجه
await router.start()

# استنتاج موزع (يتم توزيع الحمل تلقائياً)
response = await router.generate(
    prompt="Explain quantum computing",
    model="llama3.2",
)
```

#### استراتيجيات موازنة الحمل

| Strategy | الوصف |
|----------|-------|
| `round_robin` | توزيع دوري |
| `least_connections` | أقل اتصالات نشطة |
| `random` | اختيار عشوائي |
| `latency` | أقل تأخير |
| `capacity` | أعلى سعة متاحة |

### 5. سجل النماذج (Model Registry)

```python
from distributed_cluster.ai.models import ModelRegistry

# إنشاء سجل
registry = ModelRegistry()

# مزامنة من Ollama
await registry.sync_from_ollama()

# قائمة النماذج
models = registry.list_models()

# تحميل نموذج
async for progress in registry.pull_model("mistral"):
    print(progress)
```

## CLI Commands

### المحادثة

```bash
# بدء محادثة تفاعلية
dc-ai chat start
dc-ai chat start --model codellama --system "You are a coding expert"

# إرسال رسالة
dc-ai chat send "What is machine learning?"
dc-ai chat send "اكتب hello world" --model llama3.2
```

### النماذج

```bash
# عرض النماذج
dc-ai model list

# تحميل نموذج
dc-ai model pull llama3.2
dc-ai model pull codellama:7b

# حذف نموذج
dc-ai model delete mistral
```

### الوكلاء

```bash
# تشغيل وكيل
dc-ai agent run "البحث عن الأخطاء في الكود"
dc-ai agent run --type coder "اكتب unit tests"
dc-ai agent run --type researcher "ابحث عن أفضل ممارسات Python"

# عرض الوكلاء المتاحين
dc-ai agent list
```

### الاستنتاج الموزع

```bash
# بدء عامل استنتاج
dc-ai inference start-worker --port 8080

# اختبار عامل
dc-ai inference test "Hello" --url http://localhost:8080
```

## REST API

عند تشغيل الخادم، تتوفر واجهة REST API:

### Endpoints

```
POST /chat/                      - إرسال رسالة
POST /chat/conversations         - إنشاء محادثة
GET  /chat/conversations         - قائمة المحادثات
GET  /chat/conversations/{id}    - تفاصيل محادثة
POST /chat/complete              - توليد نص مباشر
GET  /chat/models                - النماذج المتاحة
WS   /chat/ws/{conversation_id}  - WebSocket للمحادثة المباشرة
```

### مثال استخدام API

```bash
# إرسال رسالة
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "model": "llama3.2"}'

# توليد مع streaming
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Write a poem", "stream": true}'
```

## التكوين - Configuration

```yaml
# config.yaml
ai:
  # LLM Provider
  provider: ollama
  ollama_url: http://localhost:11434
  default_model: llama3.2

  # Generation defaults
  temperature: 0.7
  max_tokens: 2048

  # Inference routing
  routing_strategy: round_robin
  health_check_interval: 30

  # Model registry
  models_dir: ~/.theend/models
```

## الهندسة المعمارية - Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
│              (CLI, Web UI, API Clients)                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Chat API / REST                          │
│              (FastAPI + WebSocket)                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│    Agents     │ │ Conversation  │ │    Model      │
│   Framework   │ │   Manager     │ │   Registry    │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │
        └────────────┬────┴─────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│               Inference Router (Load Balancer)              │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   Inference   │ │   Inference   │ │   Inference   │
│   Worker #1   │ │   Worker #2   │ │   Worker #N   │
│   (Ollama)    │ │   (vLLM)      │ │   (OpenAI)    │
└───────────────┘ └───────────────┘ └───────────────┘
```

## أمثلة متقدمة - Advanced Examples

### تنفيذ موزع للوكلاء

```python
from distributed_cluster.ai.agents import AgentExecutor, ExecutionConfig, ExecutionMode

# تكوين التنفيذ الموزع
config = ExecutionConfig(
    mode=ExecutionMode.DISTRIBUTED,
    master_url="http://master:8000",
    max_concurrent=5,
)

# إنشاء المنفذ
executor = AgentExecutor(config)

# تسجيل الوكلاء
executor.register_agent(general_agent)
executor.register_agent(code_agent)

# بدء المنفذ
await executor.start()

# تنفيذ مهمة
result = await executor.execute(
    agent_name="coder",
    task_description="Write a REST API for user management",
)
```

### سير عمل متعدد الوكلاء

```python
from distributed_cluster.ai.agents import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator(executor)

# تعريف سير عمل
orchestrator.define_workflow("code_review", [
    {"agent": "coder", "task": "Analyze the code in {file_path}", "output": "analysis"},
    {"agent": "researcher", "task": "Find best practices for {analysis}", "output": "practices"},
    {"agent": "coder", "task": "Suggest improvements based on {practices}", "output": "suggestions"},
])

# تشغيل سير العمل
result = await orchestrator.run_workflow(
    "code_review",
    initial_context={"file_path": "src/main.py"},
)
```

## المساهمة - Contributing

نرحب بالمساهمات! راجع [CONTRIBUTING.md](CONTRIBUTING.md) للتفاصيل.

## الترخيص - License

MIT License
