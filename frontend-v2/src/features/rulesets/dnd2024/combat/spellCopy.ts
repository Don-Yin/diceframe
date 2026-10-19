export function spellCopy(locale: string) {
  const copy = {
    'zh-CN': {
      hit: '命中后追加法术', hitHint: '攻击已命中。可追加至圣斩，或直接结算这次攻击的伤害。', decline: '不追加法术，结算攻击', free: '职业免费次数（长休恢复）',
      reasons: { not_your_turn: '尚未轮到你的角色', not_automated: '尚未接入战斗自动结算', requires_melee_hit: '近战武器或徒手攻击命中后可用', finish_melee_hit: '请先结算本次命中', action_spent: '所需动作本回合已用完', slot_already_spent: '本回合已消耗过法术位', no_spell_slot: '没有可用法术位或免费次数' },
    },
    en: {
      hit: 'Spell after a melee hit', hitHint: 'The attack hit. Add Divine Smite or resolve the attack damage.', decline: 'Resolve attack without a spell', free: 'Free class use (Long Rest)',
      reasons: { not_your_turn: 'It is not your turn', not_automated: 'Combat automation is not implemented', requires_melee_hit: 'Available after a melee weapon or Unarmed Strike hits', finish_melee_hit: 'Resolve the pending hit first', action_spent: 'Required action already spent', slot_already_spent: 'A spell slot was already spent this turn', no_spell_slot: 'No available spell slot or free use' },
    },
    de: {
      hit: 'Zauber nach einem Nahkampftreffer', hitHint: 'Der Angriff trifft. Ergänze Divine Smite oder verrechne den Schaden.', decline: 'Angriff ohne Zauber verrechnen', free: 'Kostenlose Klassennutzung (Lange Rast)',
      reasons: { not_your_turn: 'Du bist noch nicht am Zug', not_automated: 'Noch keine automatische Kampfauflösung', requires_melee_hit: 'Nach einem Nahkampf- oder waffenlosen Treffer verfügbar', finish_melee_hit: 'Zuerst den ausstehenden Treffer auflösen', action_spent: 'Benötigte Aktion bereits verbraucht', slot_already_spent: 'Diese Runde wurde bereits ein Zauberplatz verbraucht', no_spell_slot: 'Kein Zauberplatz oder kostenlose Nutzung verfügbar' },
    },
    ja: {
      hit: '近接攻撃の命中後に呪文を追加', hitHint: '攻撃が命中しました。Divine Smite を追加するか、攻撃のダメージを確定します。', decline: '呪文を追加せず攻撃を確定', free: 'クラスの無料使用（大休憩で回復）',
      reasons: { not_your_turn: 'まだあなたのターンではありません', not_automated: '戦闘の自動処理は未対応', requires_melee_hit: '近接武器か素手攻撃の命中後に使用可能', finish_melee_hit: '先に命中した攻撃を確定してください', action_spent: '必要なアクションは使用済み', slot_already_spent: 'このターンは呪文スロットを消費済み', no_spell_slot: '使用可能な呪文スロットや無料使用はありません' },
    },
    ru: {
      hit: 'Заклинание после попадания в ближнем бою', hitHint: 'Атака попала. Добавьте Divine Smite или примените урон атаки.', decline: 'Применить урон без заклинания', free: 'Бесплатное применение класса (долгий отдых)',
      reasons: { not_your_turn: 'Сейчас не ваш ход', not_automated: 'Автоматический расчёт в бою ещё не реализован', requires_melee_hit: 'Доступно после попадания оружием ближнего боя или безоружной атакой', finish_melee_hit: 'Сначала завершите расчёт попадания', action_spent: 'Необходимое действие уже потрачено', slot_already_spent: 'В этот ход уже потрачена ячейка заклинаний', no_spell_slot: 'Нет доступной ячейки или бесплатного применения' },
    },
  }
  return copy[locale as keyof typeof copy] || copy.en
}
