"""Bundled lore content migration —— 内置世界书模板内容的版本升级。

与 :mod:`src.migrations.lorebook`（SQLite schema migration，由 ``PRAGMA
user_version`` 驱动）分工不同，本模块处理的是**内容**迁移，不属于任何 schema
版本：#170 重审计把内置模板条目拆成公开/秘密两半，而
``ensure_world_from_template`` 对已存在的条目 id 直接跳过，老安装里重审计的
公开常识因此永远生效不了。执行时机由 ``src.lorebook.bootstrap`` 的
bootstrap / seed 阶段编排，本模块只负责判定与升级：

    数据库条目与重审计前官方默认快照逐字段完全一致（用户从未编辑）
        → 升级到本次迁移发布时冻结的目标状态
    用户改过任意一个受保护字段
        → 跳过，绝不触碰（用户数据绝不能被系统模板覆盖）

升级完成后条目不再等于旧官方快照，天然幂等。这是有条件的一次性官方默认
数据升级，不是模板同步系统。

迁移目标是**冻结**的（``LEGACY_BUNDLED_UPDATES``）：只包含重审计当时有意
改变的字段，取值定格在本次迁移发布时。未来模板内容变化属于**新的**迁移，
不得追溯改写本次结果——否则同一旧版本会因执行时机不同而迁移到不同状态，
违反“已发布迁移的历史语义不应被静默改写”。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("trpg")

# 与 src/lorebook/store.py ``update_entry`` 白名单一致的用户可编辑语义字段。
# 比较前对两侧做 schema 默认值归一化（缺字段 / null / "" / [] / 0 / false
# 等价），但只吸收默认值差异，不做语义等价宽松比较——归一化绝不能把真实
# 用户修改抹平。时间戳（created_at / updated_at）不参与判定。
PROTECTED_FIELDS: tuple[str, ...] = (
    "name", "type", "keywords", "content", "unreliable", "sync_on_enter",
    "tier", "triggers_recursive", "visible_to", "is_constant", "match_mode",
    "sticky", "cooldown", "delay", "order", "probability", "group",
    "group_weight", "connected_to",
)

_FIELD_DEFAULTS: dict[str, Any] = {
    "name": "",
    "type": "other",
    "keywords": [],
    "content": "",
    "unreliable": False,
    "sync_on_enter": False,
    "tier": "background",
    "triggers_recursive": [],
    "visible_to": [],
    "is_constant": False,
    "match_mode": "any",
    "sticky": 0,
    "cooldown": 0,
    "delay": 0,
    "order": 100,
    "probability": 100,
    "group": "",
    "group_weight": 1,
    "connected_to": [],
}

_LIST_FIELDS = frozenset({"keywords", "triggers_recursive", "visible_to", "connected_to"})
_BOOL_FIELDS = frozenset({"unreliable", "sync_on_enter", "is_constant"})
_INT_FIELDS = frozenset({"sticky", "cooldown", "delay", "order", "probability", "group_weight"})

# world_id -> entry_id -> 重审计**之前**的官方默认条目快照（完整 before
# 状态；稀疏存储，缺失字段即 schema 默认值）。仅用于 pristine / 用户编辑
# 判定，不参与升级目标。
LEGACY_BUNDLED_ENTRIES: dict[str, dict[str, dict[str, Any]]] = {
    'coc_horror': {
        'event_fishermen_missing': {
            'content': '过去三个月，阿卡姆港有三艘渔船出海后未归，共7名渔民失踪。唯一回来的渔民精神失常，整日念叨着「绿色的光」和「海底的城市」。当地报纸对此含糊其词，但镇民间私下议论纷纷。',
            'keywords': ['失踪', '渔民', '渔夫', '深海'],
            'name': '渔夫失踪事件',
            'tier': 'core',
            'type': 'event',
        },
        'loc_arkham': {
            'content': '位于美国马萨诸塞州东海岸的古老大学城。密斯卡托尼克大学是小镇的心脏，拥有全美最大的神秘学书籍收藏。镇上建筑多为殖民地风格，街道狭窄曲折。当地人对外来者态度警惕但不失礼貌。靠海的一侧有渔港，最近渔民们都不太愿意出海。',
            'keywords': ['阿卡姆', '小镇', '大学城', '马萨诸塞'],
            'name': '阿卡姆镇',
            'tier': 'core',
            'type': 'location',
        },
        'loc_fishing_port': {
            'content': '阿卡姆镇东侧的渔港。空气中弥漫着鱼腥和海水的味道。码头上绑着几艘渔船，其中一艘船的船身上有奇怪的抓痕——不像是正常的磨损。港口的灯塔在夜间会自动亮起，但最近灯塔管理员声称看到海面上有「绿色的磷光」。',
            'keywords': ['渔港', '港口', '码头', '海边'],
            'name': '阿卡姆渔港',
            'tier': 'core',
            'type': 'location',
        },
        'loc_howard_house': {
            'content': '位于阿卡姆镇东区的一栋二层木制老宅，门牌号榆树街13号。院中草木杂乱，信箱塞满了未取的信件。邻居说最近夜间看到二楼书房的灯会亮起，但白天窗帘紧闭，敲门无人应答。后院有个上了锁的工具棚。',
            'keywords': ['霍华德的家', '住所', '房子', '窗户'],
            'name': '霍华德的住所',
            'tier': 'core',
            'type': 'location',
        },
        'loc_miskatonic': {
            'content': '成立于1690年的古老大学。图书馆的禁书区收藏着《死灵之书》的拉丁文译本残篇、《无名祭祀书》等禁忌典籍，只有持教授签字的许可才能进入。霍华德教授的办公室在考古学系楼的三层，门牌号307。',
            'keywords': ['密斯卡托尼克大学', '大学', '图书馆', '禁书'],
            'name': '密斯卡托尼克大学',
            'tier': 'core',
            'type': 'location',
        },
        'npc_howard': {
            'content': '密斯卡托尼克大学考古学系教授，45岁。你的远房表亲。半年前带队前往南太平洋波纳佩岛考古发掘，回来后人就变得沉默寡言。最近一个月完全失联——他的办公室被锁，同事说他请了病假。但据他邻居说，夜间偶尔看到他家的窗户亮着灯，窗帘紧闭。',
            'keywords': ['霍华德', '教授', '表亲', '发信人', '考古学教授'],
            'name': '霍华德教授',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'coc_horror_en': {
        'event_missing_fishermen': {
            'content': "Over the past three months, three fishing boats have failed to return to Arkham port, leaving seven fishermen missing. The one fisherman who came back is out of his wits, mumbling day and night about a 'green light' and a 'city under the sea.' The local paper is evasive on the matter, but townsfolk whisper among themselves.",
            'keywords': ['missing', 'fishermen', 'deep sea'],
            'name': 'Missing Fishermen',
            'tier': 'core',
            'type': 'event',
        },
        'loc_arkham': {
            'content': "An old college town on the eastern coast of Massachusetts. Miskatonic University is its heart, and its library holds the largest collection of occult works in the United States. The town's architecture is largely colonial, with narrow winding streets. Locals treat outsiders with wary courtesy. The seaward side has a fishing port, but lately the fishermen have been reluctant to put out to sea.",
            'keywords': ['Arkham', 'town', 'college town', 'Massachusetts'],
            'name': 'Arkham',
            'tier': 'core',
            'type': 'location',
        },
        'loc_arkham_fishing_port': {
            'content': "The fishing port on the east side of Arkham. The air hangs thick with the smell of fish and saltwater. Several fishing boats are tied at the dock, and one of them bears strange scratch marks along its hull, nothing like ordinary wear. The harbor lighthouse lights itself at night, but its keeper now reports seeing a 'green phosphorescence' out on the water.",
            'keywords': ['fishing port', 'harbor', 'dock', 'seaside'],
            'name': 'Arkham Fishing Port',
            'tier': 'core',
            'type': 'location',
        },
        'loc_howard_residence': {
            'content': 'A two-story wooden house on the east side of Arkham, 13 Elm Street. The yard is overgrown, and the mailbox is crammed with uncollected letters. Neighbors say a light comes on in the upstairs study at night, but by day the curtains stay drawn and knocking brings no answer. A locked tool shed stands at the back.',
            'keywords': ["Howard's home", 'residence', 'house', 'windows'],
            'name': "Howard's Residence",
            'tier': 'core',
            'type': 'location',
        },
        'loc_miskatonic_university': {
            'content': "Founded in 1690, an ancient university. The library's restricted shelves hold forbidden volumes including fragments of a Latin translation of the Necronomicon and the Unaussprechlichen Kulten. Access requires a pass signed by a professor. Professor Howard's office is on the third floor of the Archaeology building, room 307.",
            'keywords': ['Miskatonic University', 'university', 'library', 'restricted books'],
            'name': 'Miskatonic University',
            'tier': 'core',
            'type': 'location',
        },
        'npc_professor_howard': {
            'content': 'A professor of archaeology at Miskatonic University, 45 years old. Your distant cousin. Six months ago he led an expedition to the island of Pohnpei in the South Pacific; since returning he has grown withdrawn and taciturn. For the past month he has been entirely out of reach: his office is locked, and colleagues say he is on sick leave. His neighbors, however, report that a light sometimes glows behind his curtains at night, always drawn tight.',
            'keywords': ['Howard', 'professor', 'cousin', 'sender', 'archaeology professor'],
            'name': 'Professor Howard',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'default_fantasy': {
        'event_forest_disturbance': {
            'content': '最近一个月，黑松林中的动物变得异常凶暴。三周前有两名猎人在林中失踪，上周有一队商人的马车在森林边缘遭到不明生物袭击。冒险者公会悬赏调查此事，赏金50金币。有目击者称看到林中深处有奇怪的光亮。',
            'keywords': ['森林异动', '失踪', '怪物', '异常'],
            'name': '森林异动',
            'tier': 'core',
            'type': 'event',
        },
        'faction_adventurer_guild': {
            'content': '遍布大陆的冒险者组织。在石桥镇的分会由一名退役冒险者「铁锤」汉克管理。公会提供任务发布、物资补给、情报交换等服务。冒险者等级从铜牌到秘银共6级。新手默认铜牌。',
            'keywords': ['冒险者公会', '公会', '任务板', '任务'],
            'name': '冒险者公会',
            'tier': 'core',
            'type': 'faction',
        },
        'loc_blackpine_forest': {
            'content': '石桥镇北面的一片广袤针叶林。林中光线昏暗，常年雾气弥漫。传闻森林深处有一座废弃的古塔，曾是某位法师的居所。近期林中的动物变得异常凶猛，有猎人在林中失踪。',
            'keywords': ['黑松林', '森林', '北边森林', '北部森林'],
            'name': '黑松林',
            'tier': 'core',
            'type': 'location',
        },
        'loc_golden_lion_inn': {
            'content': '冒险者小镇「石桥镇」中心最大的酒馆和旅馆。一楼是吧台和散座大厅，二楼有8间客房（每晚5银币）。公告板上张贴着各种任务和悬赏。酒馆的招牌菜是烤野猪肉和蜂蜜麦酒。',
            'keywords': ['金狮酒馆', '酒馆', '镇中心', '旅馆'],
            'name': '金狮酒馆',
            'tier': 'core',
            'type': 'location',
        },
        'loc_stonebridge': {
            'content': '位于艾泽兰王国北境的中型城镇，人口约2000。镇子因一座古老的石桥得名。主要建筑：金狮酒馆、冒险者公会、铁匠铺、杂货店、神殿。镇北是通往黑松林的官道，镇南通往王都。',
            'keywords': ['石桥镇', '小镇', '城镇', '冒险者公会'],
            'name': '石桥镇',
            'tier': 'core',
            'type': 'location',
        },
        'npc_blacksmith': {
            'content': '石桥镇唯一的铁匠，矮人血统，脾气火爆但手艺精湛。可以维修和购买武器防具。偶尔会有自己打造的精品装备出售（价格不菲）。对矿石品质很挑剔。',
            'keywords': ['铁匠', '杜兰', '铁匠铺', '装备', '武器'],
            'name': '铁匠杜兰',
            'type': 'npc',
        },
        'npc_innkeeper': {
            'content': '金狮酒馆的老板，50多岁，秃顶微胖，总是笑呵呵的。在镇上经营酒馆30年，认识三教九流的人，消息灵通但从不主动惹事。对冒险者态度友好，愿意提供一些本地情报。',
            'keywords': ['酒馆老板', '老汤姆', '金狮酒馆', '老板'],
            'name': '老汤姆',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'default_fantasy_en': {
        'event_forest_disturbance': {
            'content': 'During the last month, animals from Blackpine Forest have become unusually aggressive. Two hunters vanished three weeks ago, and a merchant wagon was attacked near the tree line last week. Witnesses claim they saw pale blue light deeper in the forest.',
            'keywords': ['forest disturbance', 'missing hunters', 'strange lights'],
            'name': 'Forest Disturbance',
            'tier': 'core',
            'type': 'event',
        },
        'faction_adventurers_guild': {
            'content': 'A loose network that posts jobs, pays rewards, brokers information, and keeps basic records on adventuring parties. The Stonebridge office is run by Hank Ironhand, a retired delver who distrusts clean boots and vague reports.',
            'keywords': ["Adventurers' Guild", 'guild', 'quest board', 'jobs'],
            'name': "Adventurers' Guild",
            'tier': 'core',
            'type': 'faction',
        },
        'loc_blackpine_forest': {
            'content': 'A vast conifer forest north of Stonebridge. The air beneath the branches is dim and cold even at noon. Hunters report violent animals, strange lights, and paths that seem to shift after sundown. An abandoned tower is rumored to stand somewhere in the deeper woods.',
            'keywords': ['Blackpine Forest', 'forest', 'northern woods'],
            'name': 'Blackpine Forest',
            'tier': 'core',
            'type': 'location',
        },
        'loc_golden_lion_inn': {
            'content': "The largest inn in Stonebridge, with a common room on the first floor and eight modest rooms upstairs. The adventurers' guild board is mounted beside the hearth. Its best-known dishes are roast boar, onion stew, and honey ale.",
            'keywords': ['Golden Lion Inn', 'inn', 'tavern', 'guild board'],
            'name': 'Golden Lion Inn',
            'tier': 'core',
            'type': 'location',
        },
        'loc_stonebridge': {
            'content': 'A market town of roughly two thousand people on the northern road. It is named for an ancient stone bridge crossing the mill river. Important places include the Golden Lion Inn, the guild office, a smithy, a shrine, and several supply shops.',
            'keywords': ['Stonebridge', 'town', "adventurers' guild"],
            'name': 'Stonebridge',
            'tier': 'core',
            'type': 'location',
        },
        'npc_old_tom': {
            'content': 'The owner of the Golden Lion Inn. He is in his fifties, cheerful, watchful, and careful about the trouble he lets through his door. After thirty years behind the bar, he knows merchants, hunters, guards, and guild agents by name. He is friendly to adventurers and can share local rumors.',
            'keywords': ['Old Tom', 'innkeeper', 'Golden Lion Inn'],
            'name': 'Old Tom',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'greymoor': {
        'faction_waykeepers': {
            'content': '维护灰沼引路灯、路标和安全路线的地方组织。他们不是军队，却掌握最可靠的道路记录，也负责在雾季寻找迷路者。',
            'keywords': ['守灯人', '路灯', '引路灯', '巡灯'],
            'name': '守灯人',
            'tier': 'core',
            'type': 'faction',
        },
        'loc_mistbound_road': {
            'content': '一条连接边境聚落的古老高埂路。道路两旁是浅沼和芦苇地，坚实路面很窄；货车离开车辙后很容易陷入泥中。',
            'keywords': ['灰沼驿道', '驿道', '货车', '车辙'],
            'name': '灰沼驿道',
            'tier': 'core',
            'type': 'location',
        },
        'npc_mira': {
            'content': '年轻的守灯学徒，熟悉灰沼驿道和日常巡灯路线。她认真、直率，在导师失踪后努力维持路灯系统，但缺少独自处理古老魔法异常的经验。',
            'keywords': ['米拉', '年轻守灯人', '守灯学徒'],
            'name': '米拉',
            'tier': 'core',
            'type': 'npc',
        },
        'region_greymoor': {
            'content': '王国边缘的低湿边境，遍布芦苇、黑水、泥炭地和零散林丘。晨昏的雾会吞没远处地标，旅行者通常依赖引路灯与守灯人的路线记录。',
            'keywords': ['灰沼', '沼泽', '边境', '薄雾'],
            'name': '灰沼',
            'tier': 'core',
            'type': 'region',
        },
    },
    'jp_isekai': {
        'event_monster_activity': {
            'content': '最近三个月，王都周边地区的魔物出现频率增加了约三成。平时只有史莱姆的下水道出现了剧毒变种，北部森林出现了原本栖息在深山的巨狼。公会将此事件的调查等级定为B级，悬赏500金币。有学者认为这可能与某个古代遗迹的封印松动有关。',
            'keywords': ['魔物', '异常', '活跃', '迷宫'],
            'name': '魔物异常活跃',
            'tier': 'core',
            'type': 'event',
        },
        'faction_demon_lord_remnants': {
            'content': '百年前被勇者击败的魔王军残余势力。如今分散在荒野和迷宫中，各自为政。其中最强的四天王残党仍在各自领地活动，但已无力组织大规模进攻。最近半年来，各地魔物活动频率明显升高，有冒险者推测可能有人在暗中统一残党。',
            'keywords': ['魔王', '魔王军', '残党', '魔物'],
            'name': '魔王军残党',
            'tier': 'core',
            'type': 'faction',
        },
        'loc_guild_hq': {
            'content': '王都中心的一座四层石造建筑。一楼是任务大厅和登记柜台，二楼是餐厅和休息室，三楼是高级冒险者的专属区域，四楼是公会管理办公室。大厅里悬挂着历代S级冒险者的画像。任务板每小时由魔法自动刷新一次。',
            'keywords': ['公会', '冒险者公会', '大厅', '总部'],
            'name': '冒险者公会总部',
            'tier': 'core',
            'type': 'location',
        },
        'loc_royal_capital': {
            'content': '人类王国艾尔德兰的首都，人口约五十万。城市以王宫为中心呈放射状布局。主要区域：商业区（装备店、药水铺、魔法道具店）、住宅区、神殿区（治愈神殿、冒险者安息所）、贵族区。城墙上终年有王国骑士团巡逻。',
            'keywords': ['王都', '圣剑城', '首都', '王城'],
            'name': '王都·圣剑城',
            'tier': 'core',
            'type': 'location',
        },
        'loc_slime_sewer': {
            'content': '王都地下的庞大水道网络。近年由于魔素浓度异常升高，下水道中开始出现魔物——主要是蓝色史莱姆和巨型老鼠。适合新人冒险者练手。有传闻说下水道深处连接着一个古老的迷宫遗迹。',
            'keywords': ['下水道', '地下', '史莱姆', '迷宫'],
            'name': '王都下水道',
            'tier': 'core',
            'type': 'location',
        },
        'npc_old_warrior': {
            'content': '公会二楼酒馆的常客，六十多岁的退役B级冒险者。年轻时曾跟随勇者队伍讨伐魔王军，现在每天在酒馆里喝酒讲故事。虽然看起来是个普通老头，但偶尔会给出非常精准的战斗建议。据说他还藏着几件传说级的装备没卖。',
            'keywords': ['老格雷', '退役冒险者', '酒馆', '老兵'],
            'name': '退役冒险者·老格雷',
            'type': 'npc',
        },
        'npc_receptionist': {
            'content': '冒险者公会总部的新人接待员，银发碧眼的少女，总是带着职业微笑。虽然看起来柔弱，但据说曾是A级冒险者。负责为新人冒险者登记和分配任务。对工作认真负责，偶尔会透露一些任务的内幕情报。',
            'keywords': ['莉莉', '接待员', '公会小姐'],
            'name': '公会接待员·莉莉',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'jp_isekai_en': {
        'event_monster_activity': {
            'content': 'Over the past three months, monster sightings around the royal capital have risen by roughly thirty percent. Poisonous variants have appeared in sewers that previously held only slimes, and giant wolves native to deep mountains have been seen in the northern woods. The guild has rated this investigation B-rank, with a bounty of 500 gold. Some scholars suspect a loosening seal on an ancient ruin may be to blame.',
            'keywords': ['monsters', 'abnormal', 'activity', 'labyrinth'],
            'name': 'Abnormal Monster Activity',
            'tier': 'core',
            'type': 'event',
        },
        'faction_demon_lord_remnants': {
            'content': "Remnants of the Demon Lord's army, defeated by the Hero a century ago. They are now scattered across the wilds and labyrinths, each faction acting on its own. The strongest of them, the Four Heavenly Kings' remnants, still operate in their respective territories but can no longer mount large-scale offensives. Over the past six months, monster activity has clearly risen across the land. Some adventurers suspect someone is secretly reuniting the remnants.",
            'keywords': ['Demon Lord', "Demon Lord's Army", 'remnants', 'monsters'],
            'name': "Demon Lord's Army Remnants",
            'tier': 'core',
            'type': 'faction',
        },
        'loc_guild_hq': {
            'content': "A four-story stone building at the heart of the royal capital. The first floor houses the quest hall and registration counter; the second floor, a dining hall and lounge; the third floor, an exclusive area for high-ranking adventurers; the fourth floor, the guild's administrative offices. Portraits of past S-rank adventurers line the hall. The quest board refreshes itself by magic once an hour.",
            'keywords': ['guild', "Adventurers' Guild", 'hall', 'headquarters'],
            'name': "Adventurers' Guild Headquarters",
            'tier': 'core',
            'type': 'location',
        },
        'loc_royal_capital': {
            'content': "Capital of the human kingdom of Eldran, with a population of roughly half a million. The city is laid out radially around the royal palace. Main districts: the commercial quarter (equipment shops, potion vendors, magical item stores), the residential quarter, the temple quarter (with the Healing Temple and the adventurers' rest hall), and the noble quarter. The city walls are patrolled year-round by the Royal Knight Order.",
            'keywords': ['royal capital', 'Holy Sword City', 'capital', 'castle'],
            'name': 'Royal Capital: Holy Sword City',
            'tier': 'core',
            'type': 'location',
        },
        'loc_slime_sewer': {
            'content': "A vast network of waterways beneath the royal capital. In recent years, an abnormal rise in mana concentration has drawn monsters into the sewers: chiefly blue slimes and giant rats. It is a good training ground for novice adventurers. Rumor holds that the sewers' deepest reaches connect to the ruins of an ancient labyrinth.",
            'keywords': ['sewers', 'underground', 'slimes', 'labyrinth'],
            'name': 'Royal Capital Sewers',
            'tier': 'core',
            'type': 'location',
        },
        'npc_old_warrior_grey': {
            'content': "A regular at the tavern on the second floor of the guild hall, a retired B-rank adventurer in his sixties. In his youth he rode with the Hero's party against the Demon Lord's army; now he spends his days drinking and telling stories. He looks like an ordinary old man, but from time to time he offers pinpoint combat advice. Rumor has it he still keeps a few pieces of legendary gear he has never sold.",
            'keywords': ['Old Grey', 'retired adventurer', 'tavern', 'veteran'],
            'name': 'Retired Adventurer Old Grey',
            'type': 'npc',
        },
        'npc_receptionist_lily': {
            'content': "The newcomers' receptionist at Adventurers' Guild headquarters, a silver-haired, blue-eyed girl who never loses her professional smile. Though she looks fragile, rumor says she was once an A-rank adventurer. She registers new adventurers and assigns quests. She takes her work seriously and occasionally lets slip insider details about certain quests.",
            'keywords': ['Lily', 'receptionist', 'guild receptionist'],
            'name': 'Guild Receptionist Lily',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'scifi_cyberpunk': {
        'loc_cloud_tower': {
            'content': '新东京市中心一座高达1003米的巨型建筑。下700层是MKG集团的总部和商业设施，上300层是超级富豪的封闭式住宅区。塔内空气由中央净化系统供应，与外界的污染空气隔离。顶部的空中花园只有持有白金通行证的人才能进入。安保是军事级别的。',
            'keywords': ['云顶塔', '上层', '富人区', '企业总部'],
            'name': '云顶塔',
            'type': 'location',
        },
        'loc_red_eye_bar': {
            'content': '涉谷地下市场B2层的酒馆。老板是一个装了义眼的前佣兵，对客人不多问。酒馆墙上挂满了各种退役武器和义体零件作为装饰。这里的规矩是：不打架、不窃听、不做生意——要交易去别处。角落里有一个加密通讯终端，投币使用。',
            'keywords': ['红眼', '酒馆', '接头地点', '酒吧'],
            'name': '红眼酒馆',
            'tier': 'core',
            'type': 'location',
        },
        'loc_shibuya_market': {
            'content': '新东京涉谷区地下的三层非法市场。地面上是光鲜的购物中心，地下则是另外一番景象。这里有贩卖二手义体的黑诊所、走私电子零件的摊位、以及各种不正规的情报贩子。市场入口藏在一家拉面店的后厨。第B2层有一家名为「红眼」的老酒馆，是黑客和佣兵们接头的地点。',
            'keywords': ['涉谷', '地下市场', '黑市', '涉谷区'],
            'name': '涉谷地下市场',
            'tier': 'core',
            'type': 'location',
        },
        'npc_market_doctor': {
            'content': '涉谷地下市场最知名的义体医生。经营着一家没有招牌的黑诊所。曾是大企业的义体研发工程师，因为非法实验被开除。赤井的技术和正规医院一样好，但收费只有三分之一。不过他的义体来源不明——有些可能是从尸体上回收的。',
            'keywords': ['义体医生', '赤井', '黑诊所', '医生'],
            'name': '义体医生赤井',
            'type': 'npc',
        },
    },
    'scifi_cyberpunk_en': {
        'loc_cloudspire': {
            'content': 'A 1,003-meter megastructure at the heart of Neo-Tokyo. The lower 700 floors house MKG headquarters and corporate retail; the upper 300 floors are a sealed residential arcology for the ultra-rich. Air inside is scrubbed by a central purification system, cut off from the smog below. The sky garden at the summit is accessible only with a platinum pass. Security is military-grade.',
            'keywords': ['Cloudspire', 'upper city', 'rich district', 'corporate headquarters'],
            'name': 'Cloudspire',
            'type': 'location',
        },
        'loc_red_eye_bar': {
            'content': 'A bar on level B2 of the Shibuya Underground. The owner is a former merc with a prosthetic eye who never asks questions. The walls are lined with decommissioned weapons and cyberware parts, more trophy than decor. House rules: no fighting, no eavesdropping, no dealing--take your business elsewhere. A coin-operated encrypted comm terminal sits in the corner.',
            'keywords': ['Red Eye', 'bar', 'meet point', 'tavern'],
            'name': 'Red Eye Bar',
            'tier': 'core',
            'type': 'location',
        },
        'loc_shibuya_market': {
            'content': "Three illegal levels buried beneath Shibuya's shopping district. Up top, the malls gleam; down here, the real business runs--black clinics selling second-hand cyberware, stalls hawking smuggled components, and brokers who deal in information that never appears on a feed. The entrance is hidden behind a ramen shop's kitchen. On level B2 sits an old bar called the Red Eye, where hackers and mercs go to talk business.",
            'keywords': ['Shibuya', 'underground market', 'black market', 'Shibuya district'],
            'name': 'Shibuya Underground Market',
            'tier': 'core',
            'type': 'location',
        },
        'npc_dr_akai': {
            'content': "The most reputed ripperdoc in the Shibuya Underground, running an unmarked clinic. Former cyberware R&D engineer at a major corp, fired for unlicensed experiments. Akai's work is as clean as a hospital's, at a third of the price--but the provenance of his implants is questionable. Some are likely harvested from the dead.",
            'keywords': ['ripperdoc', 'Akai', 'black clinic', 'doctor'],
            'name': 'Dr. Akai',
            'type': 'npc',
        },
    },
    'tavern_generic': {
        'tavern_owner': {
            'content': '酒馆老板，五十多岁，左臂有旧伤。不问客人来路，但记得每个老顾客的喜好。偶尔会给有缘人透露一些情报。',
            'name': '老莫',
            'tier': 'core',
            'type': 'npc',
        },
        'tavern_place': {
            'content': '两层木石结构，一楼是大厅和吧台，二楼是客房。后院有马厍和仓库。老板名叫老莫，是个退休的冒险者。',
            'name': '十字路口酒馆',
            'tier': 'core',
            'type': 'location',
        },
    },
    'tavern_generic_en': {
        'loc_crossroads_inn': {
            'content': 'A two-story timber-and-stone building. The first floor holds the common room and bar; the second floor has guest rooms. The back yard contains a stable and a storehouse. The innkeeper is named Old Mo, a retired adventurer.',
            'name': 'Crossroads Inn',
            'tier': 'core',
            'type': 'location',
        },
        'npc_old_mo': {
            'content': "The innkeeper, in his fifties, with an old wound on his left arm. He never asks guests where they come from, but he remembers every regular's preferences.",
            'name': 'Old Mo',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'zhongshi_fantasy': {
        'event_strange_light': {
            'content': '近一个月来，枯木崖顶夜夜出现诡异绿光，持续约一炷香时间。镇民人心惶惶，已有人搬离。青石镇镇长发话：谁能查明真相，赏银百两。有老猎人说那绿光像是「妖丹」的光芒——有妖物在崖下修炼。',
            'keywords': ['异光', '绿光', '妖物出没', '怪事'],
            'name': '枯木崖异光',
            'tier': 'core',
            'type': 'event',
        },
        'faction_kunlun_sword_sect': {
            'content': '西部第一剑道宗门，坐落于昆仑山脉中。以「昆仑十三剑」闻名天下。现任掌门「剑圣」独孤寒，据说是当世仅存的几位分神境高手之一。剑宗弟子行事正派，以降妖除魔为己任。每隔三年开山收徒一次，天下少年皆以拜入剑宗为荣。',
            'keywords': ['昆仑剑宗', '剑宗', '昆仑', '剑道'],
            'name': '昆仑剑宗',
            'tier': 'core',
            'type': 'faction',
        },
        'loc_kumu_cliff': {
            'content': '青石镇以西三里处的一座陡峭山崖。崖顶有一棵千年枯松，故名枯木崖。崖下有数个天然石洞，据说是古代修士的洞府遗迹。近一个月来，夜间崖顶常出现诡异绿光，有采药人声称看到洞中有妖物出没。',
            'keywords': ['枯木崖', '山崖', '妖物', '异光'],
            'name': '枯木崖',
            'tier': 'core',
            'type': 'location',
        },
        'loc_qingshi': {
            'content': '大夏王朝西部边陲的小镇，因镇外青石崖而得名。人口约1500，半农半猎。镇上有茶馆、药铺、铁匠铺和一间小客栈「清风居」。每月逢五有集市，远近山民都会来此交易。镇子虽小，但地处通往昆仑山脉的要道，过往的江湖人士不少。',
            'keywords': ['青石镇', '小镇', '边陲', '集市'],
            'name': '青石镇',
            'tier': 'core',
            'type': 'location',
        },
        'npc_herbalist': {
            'content': '青石镇的采药老人，六十多岁，在枯木崖一带采药三十余年。三天前在崖下采药时目睹洞中有「人形黑影」闪过，吓得连夜跑回镇子。老王口吃，说话吞吞吐吐，但为人老实不撒谎。',
            'keywords': ['采药人', '老王', '王伯', '目击者'],
            'name': '采药人老王',
            'type': 'npc',
        },
        'npc_teahouse_owner': {
            'content': '清风茶馆的老板，四十来岁，面容清瘦但双目有神。据说是从京城退隐来此的，来历不明。茶馆是镇上的消息集散地，柳掌柜消息灵通，对江湖事了如指掌，但从不主动透露自己的事。',
            'keywords': ['柳掌柜', '茶馆老板', '清风茶馆', '掌柜'],
            'name': '柳掌柜',
            'tier': 'core',
            'type': 'npc',
        },
    },
    'zhongshi_fantasy_en': {
        'event_deadwood_cliff_strange_light': {
            'content': "For the past month, eerie green light has appeared atop Deadwood Cliff every night, lasting about the time it takes to burn a stick of incense. The townsfolk are in a panic, and some have already moved away. The mayor of Bluestone Town has offered a hundred taels of silver to anyone who can uncover the truth. An old hunter says the green light looks like the glow of a 'demon core'—a monster is cultivating beneath the cliff.",
            'keywords': ['strange light', 'green light', 'monster sighting', 'uncanny events'],
            'name': 'Strange Light at Deadwood Cliff',
            'tier': 'core',
            'type': 'event',
        },
        'faction_kunlun_sword_sect': {
            'content': "The foremost swordsmanship sect in the west, seated among the Kunlun Mountains. It is renowned across the land for the 'Thirteen Swords of Kunlun.' Its current sect master, Dugu Han, known as the 'Sword Saint,' is said to be one of the few Spirit Split realm masters left in the world. Disciples of the Sword Sect act with righteousness and take slaying demons and evil as their duty. The sect opens its gates to take in new disciples once every three years, and youths across the realm consider it an honor to be accepted.",
            'keywords': ['Kunlun Sword Sect', 'Sword Sect', 'Kunlun', 'swordsmanship'],
            'name': 'Kunlun Sword Sect',
            'tier': 'core',
            'type': 'faction',
        },
        'loc_bluestone_town': {
            'content': 'A small town on the western frontier of the Great Xia Dynasty, named for the Bluestone Cliff just outside. Its population of about 1,500 lives by farming and hunting. The town has a teahouse, an apothecary, a smithy, and a small inn called the Clear Breeze Lodge. On every fifth day a market is held, drawing mountain folk from all around to trade. Though small, the town sits on the main road to the Kunlun Mountains, and many wandering figures of the martial world pass through.',
            'keywords': ['Bluestone Town', 'town', 'frontier', 'market'],
            'name': 'Bluestone Town',
            'tier': 'core',
            'type': 'location',
        },
        'loc_deadwood_cliff': {
            'content': "A steep cliff three li west of Bluestone Town. A millennia-old withered pine stands atop it, giving the cliff its name. At its foot lie several natural stone caves, said to be the ruins of an ancient cultivator's dwelling. For the past month, eerie green light has been appearing atop the cliff at night, and a herbalist claims to have seen a monster moving inside the caves.",
            'keywords': ['Deadwood Cliff', 'cliff', 'monster', 'strange light'],
            'name': 'Deadwood Cliff',
            'tier': 'core',
            'type': 'location',
        },
        'npc_old_wang_herbalist': {
            'content': "An elderly herbalist of Bluestone Town, in his sixties, who has gathered herbs around Deadwood Cliff for over thirty years. Three days ago, while picking herbs beneath the cliff, he caught sight of a 'human-shaped shadow' flitting through the caves and fled back to town in the dead of night. Old Wang stutters and speaks haltingly, but he is an honest man who does not lie.",
            'keywords': ['herbalist', 'Old Wang', 'Uncle Wang', 'witness'],
            'name': 'Old Wang the Herbalist',
            'type': 'npc',
        },
        'npc_shopkeeper_liu': {
            'content': "Owner of the Clear Breeze Teahouse. He is in his forties, thin-faced but with bright, spirited eyes. Word is he retired here from the capital years ago, though his true background remains unknown. The teahouse is the town's hub of news and gossip; Shopkeeper Liu is well-informed and knows the martial world inside out, though he never volunteers anything about himself.",
            'keywords': ['Shopkeeper Liu', 'teahouse owner', 'Clear Breeze Teahouse', 'shopkeeper'],
            'name': 'Shopkeeper Liu',
            'tier': 'core',
            'type': 'npc',
        },
    },
}

# world_id -> entry_id -> 本次迁移发布时冻结的 after / update payload。
# 只包含重审计当时有意改变的字段（公开化条目为 visible_to；拆分/裁剪条目
# 为 content + visible_to），取值定格在迁移发布时的官方版本。升级目标不取
# 自实时模板：未来模板变化属于新的迁移，不得追溯改变已发布迁移的结果。
LEGACY_BUNDLED_UPDATES: dict[str, dict[str, dict[str, Any]]] = {
    'coc_horror': {
        'event_fishermen_missing': {
            'visible_to': ['*'],
        },
        'loc_arkham': {
            'visible_to': ['*'],
        },
        'loc_fishing_port': {
            'content': '阿卡姆镇东侧的渔港，空气中弥漫着鱼腥和海水的味道。近来渔民们都不太愿意出海，码头上比往常冷清了许多。',
            'visible_to': ['*'],
        },
        'loc_howard_house': {
            'content': '位于阿卡姆镇东区的一栋二层木制老宅，门牌号榆树街13号。镇上人都知道这是霍华德教授的宅子；最近宅门紧闭，敲门始终无人应答。',
            'visible_to': ['*'],
        },
        'loc_miskatonic': {
            'visible_to': ['*'],
        },
        'npc_howard': {
            'content': '密斯卡托尼克大学考古学系教授，45岁。你的远房表亲。半年前带队前往南太平洋波纳佩岛考古发掘，回来后人就变得沉默寡言。最近一个月完全失联——他的办公室被锁，同事说他请了病假。',
            'visible_to': ['*'],
        },
    },
    'coc_horror_en': {
        'event_missing_fishermen': {
            'visible_to': ['*'],
        },
        'loc_arkham': {
            'visible_to': ['*'],
        },
        'loc_arkham_fishing_port': {
            'content': 'The fishing port on the east side of Arkham. The air hangs thick with the smell of fish and saltwater. Lately the fishermen have been reluctant to put out to sea, and the docks are quieter than usual.',
            'visible_to': ['*'],
        },
        'loc_howard_residence': {
            'content': "A two-story wooden house on the east side of Arkham, 13 Elm Street. Everyone in town knows it as Professor Howard's house; lately the house has stayed shut, with no answer at the door.",
            'visible_to': ['*'],
        },
        'loc_miskatonic_university': {
            'visible_to': ['*'],
        },
        'npc_professor_howard': {
            'content': 'A professor of archaeology at Miskatonic University, 45 years old. Your distant cousin. Six months ago he led an expedition to the island of Pohnpei in the South Pacific; since returning he has grown withdrawn and taciturn. For the past month he has been entirely out of reach: his office is locked, and colleagues say he is on sick leave.',
            'visible_to': ['*'],
        },
    },
    'default_fantasy': {
        'event_forest_disturbance': {
            'visible_to': ['*'],
        },
        'faction_adventurer_guild': {
            'visible_to': ['*'],
        },
        'loc_blackpine_forest': {
            'visible_to': ['*'],
        },
        'loc_golden_lion_inn': {
            'visible_to': ['*'],
        },
        'loc_stonebridge': {
            'visible_to': ['*'],
        },
        'npc_blacksmith': {
            'visible_to': ['*'],
        },
        'npc_innkeeper': {
            'visible_to': ['*'],
        },
    },
    'default_fantasy_en': {
        'event_forest_disturbance': {
            'visible_to': ['*'],
        },
        'faction_adventurers_guild': {
            'visible_to': ['*'],
        },
        'loc_blackpine_forest': {
            'visible_to': ['*'],
        },
        'loc_golden_lion_inn': {
            'visible_to': ['*'],
        },
        'loc_stonebridge': {
            'visible_to': ['*'],
        },
        'npc_old_tom': {
            'visible_to': ['*'],
        },
    },
    'greymoor': {
        'faction_waykeepers': {
            'visible_to': ['*'],
        },
        'loc_mistbound_road': {
            'visible_to': ['*'],
        },
        'npc_mira': {
            'visible_to': ['*'],
        },
        'region_greymoor': {
            'visible_to': ['*'],
        },
    },
    'jp_isekai': {
        'event_monster_activity': {
            'visible_to': ['*'],
        },
        'faction_demon_lord_remnants': {
            'visible_to': ['*'],
        },
        'loc_guild_hq': {
            'visible_to': ['*'],
        },
        'loc_royal_capital': {
            'visible_to': ['*'],
        },
        'loc_slime_sewer': {
            'visible_to': ['*'],
        },
        'npc_old_warrior': {
            'visible_to': ['*'],
        },
        'npc_receptionist': {
            'visible_to': ['*'],
        },
    },
    'jp_isekai_en': {
        'event_monster_activity': {
            'visible_to': ['*'],
        },
        'faction_demon_lord_remnants': {
            'visible_to': ['*'],
        },
        'loc_guild_hq': {
            'visible_to': ['*'],
        },
        'loc_royal_capital': {
            'visible_to': ['*'],
        },
        'loc_slime_sewer': {
            'visible_to': ['*'],
        },
        'npc_old_warrior_grey': {
            'visible_to': ['*'],
        },
        'npc_receptionist_lily': {
            'visible_to': ['*'],
        },
    },
    'scifi_cyberpunk': {
        'loc_cloud_tower': {
            'visible_to': ['*'],
        },
        'loc_red_eye_bar': {
            'visible_to': ['*'],
        },
        'loc_shibuya_market': {
            'content': '新东京涉谷区地下藏着三层的非法市场：二手义体的黑诊所、走私电子零件的摊位，以及各式情报贩子。圈外人多半当它是都市传说，混迹地下的人却都知道确有其事。',
            'visible_to': ['*'],
        },
        'npc_market_doctor': {
            'visible_to': ['*'],
        },
    },
    'scifi_cyberpunk_en': {
        'loc_cloudspire': {
            'visible_to': ['*'],
        },
        'loc_red_eye_bar': {
            'visible_to': ['*'],
        },
        'loc_shibuya_market': {
            'content': "Three illegal levels buried beneath Shibuya's shopping district. Up top, the malls gleam; down here, the real business runs--black clinics selling second-hand cyberware, stalls hawking smuggled components, and brokers dealing in information that never appears on a feed. Outsiders call it an urban legend; the underground knows better.",
            'visible_to': ['*'],
        },
        'npc_dr_akai': {
            'visible_to': ['*'],
        },
    },
    'tavern_generic': {
        'tavern_owner': {
            'visible_to': ['*'],
        },
        'tavern_place': {
            'visible_to': ['*'],
        },
    },
    'tavern_generic_en': {
        'loc_crossroads_inn': {
            'visible_to': ['*'],
        },
        'npc_old_mo': {
            'visible_to': ['*'],
        },
    },
    'zhongshi_fantasy': {
        'event_strange_light': {
            'visible_to': ['*'],
        },
        'faction_kunlun_sword_sect': {
            'visible_to': ['*'],
        },
        'loc_kumu_cliff': {
            'visible_to': ['*'],
        },
        'loc_qingshi': {
            'visible_to': ['*'],
        },
        'npc_herbalist': {
            'visible_to': ['*'],
        },
        'npc_teahouse_owner': {
            'visible_to': ['*'],
        },
    },
    'zhongshi_fantasy_en': {
        'event_deadwood_cliff_strange_light': {
            'visible_to': ['*'],
        },
        'faction_kunlun_sword_sect': {
            'visible_to': ['*'],
        },
        'loc_bluestone_town': {
            'visible_to': ['*'],
        },
        'loc_deadwood_cliff': {
            'visible_to': ['*'],
        },
        'npc_old_wang_herbalist': {
            'visible_to': ['*'],
        },
        'npc_shopkeeper_liu': {
            'visible_to': ['*'],
        },
    },
}


def _canonical_field(field: str, value: Any) -> Any:
    """把一个字段归一化成持久化形状；只吸收 schema 默认值差异。"""
    if field in _LIST_FIELDS:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                decoded = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                decoded = [part.strip() for part in text.split(",")]
            value = decoded
        if not isinstance(value, (list, tuple, set)):
            value = [value]
        return [str(item).strip() for item in value if str(item).strip()]
    if field in _BOOL_FIELDS:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if field in _INT_FIELDS:
        if value is None or value == "":
            return _FIELD_DEFAULTS[field]
        try:
            return int(value)
        except (TypeError, ValueError):
            return _FIELD_DEFAULTS[field]
    return _FIELD_DEFAULTS[field] if value is None else str(value)


def _canonical_entry(source: dict[str, Any]) -> dict[str, Any]:
    return {field: _canonical_field(field, source.get(field)) for field in PROTECTED_FIELDS}


def maybe_upgrade_bundled_entry(lorebook_store: Any, world_id: str, entry_id: str, bundled: dict[str, Any]) -> None:
    """存量条目仍是重审计前官方默认（用户从未编辑）时，升级到冻结的迁移目标。

    由 bootstrap / seed 阶段对每个模板条目调用。zh/en 模板共享条目 id 时，
    后 seed 的一方在 ``ensure_world_from_template`` 里被改名成
    ``f"{world_id}_{entry_id}"``，这里同样要在改名后的行上完成升级。

    ``bundled``（当前实时模板条目）**不参与**升级目标：目标一律来自
    ``LEGACY_BUNDLED_UPDATES`` 的冻结 payload。该参数仅为维持调用点签名
    稳定而保留，这样未来模板如何演进都不会影响本次已发布迁移的结果。
    """
    legacy = LEGACY_BUNDLED_ENTRIES.get(world_id, {}).get(entry_id)
    if legacy is None:
        return
    updates = LEGACY_BUNDLED_UPDATES.get(world_id, {}).get(entry_id)
    if not updates:
        return
    db_id = entry_id
    existing = lorebook_store.get_entry(db_id)
    if not existing or existing.get("world_id") != world_id:
        db_id = f"{world_id}_{entry_id}"
        existing = lorebook_store.get_entry(db_id)
    if not existing or existing.get("world_id") != world_id:
        return
    recorded = _canonical_entry(legacy)
    stored = _canonical_entry(existing)
    if any(stored[field] != recorded[field] for field in PROTECTED_FIELDS):
        return  # 任一字段偏离旧官方默认：用户编辑过或已是新版 → 保留现状
    payload = {field: _canonical_field(field, value) for field, value in updates.items()}
    lorebook_store.update_entry(db_id, payload)
    logger.info("内置世界书条目已升级到已发布迁移目标: %s/%s", world_id, db_id)
