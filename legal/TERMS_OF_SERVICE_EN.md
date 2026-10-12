# DiceFrame Terms of Use

Last updated: August 20, 2026
Effective date: August 20, 2026
Version: 1.1

Please read these Terms and the DiceFrame Privacy Policy before downloading, installing, deploying, or using DiceFrame.

**By actively confirming that you have read and agree, you accept these Terms. If you disagree, stop using DiceFrame. Optional usage statistics require a separate choice and are not enabled merely by accepting these Terms.**

## 1. Project and scope

DiceFrame is a self-hosted, open-source AI tabletop role-playing tool released under the GNU Affero General Public License v3.0 (AGPL-3.0). Its official source and releases are at [diceframe/diceframe](https://github.com/diceframe/diceframe). “Maintainers” means individual open-source contributors maintaining that repository. DiceFrame is an open-source collaboration, not a company, platform agent, game operator, or professional service created by these Terms.

These Terms cover official DiceFrame releases, its web interface, and public index or Hub services actually operated by the maintainers. Independent plugins, model providers, tunnels, mirrors, and derivative projects have their own terms. Users under 18 or without full legal capacity should use DiceFrame only with a guardian's review and consent.

## 2. Open-source license

You may use, study, modify, and distribute DiceFrame under AGPL-3.0. These Terms do not reduce rights granted by that license; AGPL-3.0 controls source-code and network-service obligations. Names, logos, website content, and third-party assets not expressly licensed are not automatically licensed for trademark use or endorsement. Do not claim a partnership, certification, agency, or authorization relationship with the maintainers without express written permission.

## 3. Self-hosting and third parties

DiceFrame primarily runs on infrastructure controlled by its deployer. The deployer chooses model providers, plugins, network exposure, sharing, and backups and is responsible for related accounts, fees, keys, security, and legal duties. AI requests send the prompt and game context needed for generation to the provider selected by the user. GitHub, DiceFrame Hub, Cloudflare, Metered, Nextcloud, NapCat, mirrors, and plugin repositories are independent services unless expressly stated otherwise.

Keep model keys, DiceFrame access passwords, bot tokens, Hub tokens, and backups secure. The deployer is responsible for risks arising from weak passwords, exposed ports, incorrect proxies, leaked credentials, or delayed updates.

Direct connection is an invitation-only feature actively enabled by users. Official Hub exchanges only short-lived WebRTC handshake signaling; after setup, participant DataChannel content does not pass through Hub. The direct-connect protocol permits only enumerated game reads and player operations, binds each participant identity at the host client, and executes operations through the host's local game engine. Hosts should confirm that the selected game, participants, and model configuration are appropriate to share. Maintainers ordinarily cannot view, recover, or proactively review DataChannel content. Hosts and participants remain responsible for lawful use, respect for others' rights, and appropriate access control.

Each client may use a listed third-party STUN option (currently Cloudflare, Metered, Nextcloud, or a multi-provider combination), use no STUN, or enter one or more third-party/self-hosted STUN URIs. Availability, data processing, international transfer, and any charges are governed by those providers and the selecting user. DiceFrame does not provide TURN, so strict NAT, CGNAT, firewalls, or third-party failure may prevent connection.

One-time link codes contain a guest secret and must be sent only to intended participants and replaced if exposed. Do not use direct connection, signaling, room codes, or custom servers for scanning, attacks, access-control evasion, unlawful content, or infringement. Official Hub may rate-limit, reject, ban sources, close handshakes, or disable the feature for security, capacity, maintenance, complaints, or compliance.

## 4. AI content and acceptable use

Generated stories, characters, rules, summaries, and other outputs may be false, fictional, offensive, unsuitable, infringing, or unexpected. They are entertainment and creative assistance, not fact, professional advice, or the views of maintainers. Review output before using or publishing it.

Do not use DiceFrame for illegal activity, harm, infringement, privacy violations, harassment, sexual exploitation of minors, fraud, or evasion of third-party rules. You must have the necessary rights for content you import or distribute. If you share a public room or chat bot, you are responsible for participant notice, access control, moderation, and age-appropriate use.

## 5. Plugins and community content

Plugins and content packs may be produced by independent authors. Listing, review state, provenance labels, signatures, counts, likes, and ratings are not warranties of security, legality, quality, or fitness. High-permission plugins can affect device security; review permissions and repositories and keep backups.

Maintainers may hide or delist entries for security, illegality, infringement, deception, or governance reasons. That does not remove local copies or revoke applicable open-source rights. Plugin authors, content authors, and mirror operators remain responsible for their own work and services.

## 6. Security, backups, and feedback

DiceFrame does not guarantee that local data, saves, keys, or plugins will never be lost, corrupted, or accessed without authorization. Use strong passwords, HTTPS, supported versions, trusted plugins, and tested offline backups.

Submit reproducible issues through [GitHub Issues](https://github.com/diceframe/diceframe/issues). Remove API keys, tokens, passwords, private chats, personal information, and full saves before posting. Public Issues and Pull Requests are visible to others. Maintainers may prioritize or close feedback according to reproducibility, safety, direction, and available resources.

## 7. Availability and disclaimers

DiceFrame, announcements, the public plugin index, Hub, mirrors, and update services are provided “as is” and “as available,” without promises of uninterrupted availability, error-free operation, universal compatibility, fitness for a particular purpose, or permanent storage.

Maintainers may rate-limit, shed load, change, suspend, or discontinue online services without revoking source-code rights already granted under AGPL-3.0. Hub unavailability, full capacity, or refusal of a new handshake does not ordinarily control local functions or an already established direct channel, but successful setup through strict NAT is not guaranteed. To the maximum extent permitted by law, maintainers are not liable for indirect, incidental, special, or consequential losses arising from DiceFrame, AI output, third-party services, plugins, public deployment, lost data, account issues, or fees. Nothing excludes liability or mandatory user rights that cannot lawfully be excluded.

## 8. Relationship and intellectual property

DiceFrame is not an official product of any tabletop publisher, video-game company, model provider, social platform, Cloudflare, NapCat, or plugin author unless a page expressly states otherwise. Third-party works and marks belong to their owners. “Fan-made,” “unofficial,” or attribution alone does not grant permission to copy, adapt, distribute, or commercialize protected material.

Maintainers are responsible only to the extent required by applicable law for code, documentation, and services they actually provide and control. They do not endorse acts of independent deployers, distributors, plugin authors, or users.

## 9. Changes and contact

Material changes will update the version and trigger a new in-app confirmation. Invalid provisions do not affect the remainder. If translations conflict, the Simplified Chinese version controls. Questions may be submitted through [GitHub Issues](https://github.com/diceframe/diceframe/issues); never post secrets or sensitive personal data publicly.
