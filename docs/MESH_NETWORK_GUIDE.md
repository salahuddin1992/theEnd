# دليل شبكة Mesh | Mesh Network Guide

## نظرة عامة | Overview

شبكة Mesh هي وضع تشغيل **لامركزي** للحوسبة الموزعة، حيث يمكن للعقد (Nodes) التواصل مباشرة بدون الحاجة لخادم Master مركزي.

```
الوضع التقليدي (Master/Worker):        وضع Mesh اللامركزي:

       ┌────────┐                       ┌────┐   ┌────┐
       │ Master │                       │Node│───│Node│
       └───┬────┘                       └─┬──┘   └──┬─┘
           │                              │    ╲   │
    ┌──────┼──────┐                       │     ╲  │
    │      │      │                     ┌─┴──┐  ┌┴─┴─┐
 ┌──┴─┐ ┌──┴─┐ ┌──┴─┐                   │Node│──│Node│
 │ W1 │ │ W2 │ │ W3 │                   └────┘  └────┘
 └────┘ └────┘ └────┘
```

## المميزات | Features

- **لا مركزي**: لا نقطة فشل واحدة
- **اكتشاف تلقائي**: العقد تكتشف بعضها تلقائياً
- **تحمل الأخطاء**: الشبكة تستمر رغم فشل بعض العقد
- **توجيه ذكي**: المهام تُوجه لأفضل عقدة
- **انتخاب القائد**: تنسيق تلقائي بين العقد

## البدء السريع | Quick Start

### 1. تشغيل العقدة الأولى

```bash
# على الجهاز الأول
dc-mesh start --port 9000
```

### 2. انضمام عقد إضافية

```bash
# على الجهاز الثاني (نفس الشبكة المحلية)
dc-mesh start --port 9000  # سيكتشف العقد تلقائياً

# أو مع تحديد عنوان للاتصال
dc-mesh start --port 9000 --bootstrap 192.168.1.10:9000
```

### 3. إرسال مهام

```bash
# إرسال مهمة بسيطة
dc-mesh submit "echo hello world"

# إرسال مهمة مع متطلبات موارد
dc-mesh submit "python train.py" --cpu 4 --memory 8192 --gpu 1
```

## طرق الاكتشاف | Discovery Methods

### 1. Multicast (افتراضي)
```bash
dc-mesh start --port 9000
# العقد في نفس الشبكة المحلية تكتشف بعضها تلقائياً
```

### 2. Bootstrap (قائمة عقد معروفة)
```bash
dc-mesh start --port 9000 \
  --bootstrap 192.168.1.10:9000 \
  --bootstrap 192.168.1.11:9000
```

### 3. Gossip (تبادل مع المتصلين)
العقد تتبادل قوائم العقد المعروفة تلقائياً.

### تعطيل Multicast
```bash
# في البيئات التي لا تدعم multicast
dc-mesh start --port 9000 --no-multicast --bootstrap 10.0.0.5:9000
```

## استراتيجيات التوجيه | Routing Strategies

| الاستراتيجية | الوصف | الاستخدام |
|-------------|-------|----------|
| `random` | اختيار عشوائي | توزيع متساوي |
| `round_robin` | بالتناوب | توزيع متساوي مرتب |
| `least_loaded` | الأقل حملاً (افتراضي) | أفضل استجابة |
| `best_fit` | أقل هدر للموارد | كفاءة الموارد |
| `nearest` | الأقرب (أقل latency) | حساسية للتأخير |
| `resource_aware` | مزيج ذكي | أفضل توازن |

```bash
# استخدام استراتيجية محددة
dc-mesh start --port 9000 --strategy best_fit
```

## انتخاب القائد | Leader Election

يستخدم النظام خوارزمية **Bully** لانتخاب قائد:

1. إذا لم تستلم العقدة heartbeat من القائد، تبدأ انتخاباً
2. العقدة ذات أعلى ID تفوز
3. القائد يرسل heartbeat كل 3 ثواني

```
العقدة ذات أعلى ID = القائد

node-aaa ─┐
node-bbb ─┼─ → node-zzz يصبح القائد
node-zzz ─┘
```

## مثال عملي كامل | Complete Example

### السيناريو: 3 أجهزة في شبكة محلية

**الجهاز 1 (192.168.1.10):**
```bash
dc-mesh start --port 9000 --tags master,storage
```

**الجهاز 2 (192.168.1.11):**
```bash
dc-mesh start --port 9000 --tags gpu --bootstrap 192.168.1.10:9000
```

**الجهاز 3 (192.168.1.12):**
```bash
dc-mesh start --port 9000 --tags compute --bootstrap 192.168.1.10:9000
```

**إرسال مهمة:**
```bash
dc-mesh submit "python heavy_computation.py" --cpu 8 --gpu 1
```

## البرمجة باستخدام API | Programming API

```python
import asyncio
from distributed_cluster.mesh import MeshNode, RoutingStrategy
from distributed_cluster.models.job import Job
from distributed_cluster.models.resources import ResourceSpec

async def main():
    # إنشاء عقدة
    node = MeshNode(
        port=9000,
        node_id="my-node",
        tags={"gpu", "high-memory"},
        routing_strategy=RoutingStrategy.LEAST_LOADED,
        bootstrap_peers=["192.168.1.10:9000"],
    )

    # معالجة الأحداث
    node.on("peer_added", lambda d: print(f"New peer: {d['peer_id']}"))
    node.on("job_completed", lambda d: print(f"Job done: {d['job_id']}"))

    # بدء العقدة
    await node.start()
    print(f"Node started: {node.node_id}")
    print(f"Connected peers: {node.peer_count}")

    # إرسال مهمة
    job = Job(
        job_id="job-001",
        command="python train.py",
        resources=ResourceSpec(cpu_cores=4, memory_mb=8192, gpu_count=1),
    )
    await node.submit_job(job)

    # انتظار
    await asyncio.sleep(60)

    # إيقاف
    await node.stop()

asyncio.run(main())
```

## الأحداث المتاحة | Available Events

| الحدث | البيانات | الوصف |
|-------|---------|-------|
| `started` | `{node_id}` | العقدة بدأت |
| `stopped` | `{node_id}` | العقدة توقفت |
| `peer_added` | `{peer_id}` | عقدة جديدة اتصلت |
| `peer_removed` | `{peer_id}` | عقدة انقطعت |
| `became_leader` | `{term}` | أصبحت القائد |
| `new_leader` | `{leader_id}` | قائد جديد انتُخب |
| `job_submitted` | `{job_id}` | مهمة أُرسلت |
| `job_started` | `{job_id}` | مهمة بدأت |
| `job_completed` | `{job_id, status}` | مهمة انتهت |

## معلومات الكلاستر | Cluster Info

```python
info = node.get_cluster_info()
print(f"""
Node ID: {info['node_id']}
State: {info['state']}
Is Leader: {info['is_leader']}
Leader ID: {info['leader_id']}
Peers: {info['peer_count']}
Local Jobs: {info['local_jobs']}
CPU: {info['resources']['cpu_cores']} cores ({info['usage']['cpu_percent']}%)
Memory: {info['resources']['memory_mb']} MB ({info['usage']['memory_percent']}%)
""")
```

## مقارنة مع الوضع التقليدي | Comparison with Master/Worker

| الميزة | Master/Worker | Mesh |
|--------|---------------|------|
| نقطة فشل واحدة | نعم (Master) | لا |
| الإعداد | أبسط | أعقد قليلاً |
| القابلية للتوسع | عالية | عالية جداً |
| التنسيق | مركزي | موزع |
| حالة الاستخدام | كلاستر صغير-متوسط | كلاستر كبير/موزع |

## متى تستخدم Mesh؟ | When to Use Mesh?

✅ **استخدم Mesh عندما:**
- تحتاج لتحمل فشل أي عقدة
- العقد موزعة جغرافياً
- لا تريد نقطة فشل واحدة
- الشبكة كبيرة (>10 عقد)

❌ **استخدم Master/Worker عندما:**
- الشبكة صغيرة (<10 عقد)
- تحتاج تحكم مركزي
- البساطة أهم من التحمل

## استكشاف الأخطاء | Troubleshooting

### العقد لا تكتشف بعضها
```bash
# تأكد من أن المنافذ مفتوحة
# جرب تعطيل multicast واستخدام bootstrap
dc-mesh start --no-multicast --bootstrap IP:PORT
```

### المهام لا تُنفذ
```bash
# تحقق من الموارد المتاحة
dc-mesh info

# تأكد من أن هناك عقد متصلة
dc-mesh start --interactive
```

### القائد يتغير باستمرار
```bash
# قد يكون هناك مشاكل في الشبكة
# تحقق من استقرار الاتصال بين العقد
```

## المراجع | References

- [Gossip Protocol](https://en.wikipedia.org/wiki/Gossip_protocol)
- [Bully Algorithm](https://en.wikipedia.org/wiki/Bully_algorithm)
- [Distributed Systems Concepts](https://en.wikipedia.org/wiki/Distributed_computing)
