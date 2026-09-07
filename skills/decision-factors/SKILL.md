---
name: decision-factors
description: Checklist des facteurs qualitatifs qui complètent l'équité brute (position, implied/reverse implied odds, SPR, fold equity/exploitabilité, joueurs restants à parler) pour une analyse de décision poker plus complète, sans recourir à un solver complet. À consulter systématiquement par range-builder, live-session et hand-review dès qu'une analyse va au-delà d'un simple chiffre d'équité — chaque fois qu'on explique un fold/call/raise en profondeur.
---

# Decision Factors

## Méthode — reconstruire la range avant de comparer au seuil (range narrowing)

**Erreur constatée en session** : calculer le seuil de rentabilité arithmétique (cotes du pot) *avant* d'avoir vérifié que la range adverse contenait encore assez de mains battues pour le justifier. Dans un cas concret, la conclusion ("il suffit de 17% de mains pires") a été donnée sans jamais vérifier que ces 17% existaient encore dans la range — c'est l'utilisateur qui a posé la question qui a fait s'effondrer le raisonnement.

**Ordre validé** (le terme technique est **"range narrowing"**, un concept standard de la théorie du poker, pas une invention de session) :
1. Construire la range de départ du villain à partir de sa position **et** de son profil (HUD/archétype) — ni l'un ni l'autre seul.
2. **Retirer** ce que chaque mise/call a filtré : un call cher élimine mécaniquement les mains les plus faibles de cette range (cf. `range-notation`/`range-builder` pour l'exprimer concrètement).
3. Appliquer l'effet de chaque carte tombée sur ce qui reste (quelles catégories de mains viennent de s'améliorer, lesquelles sont mortes).
4. **Seulement ensuite** comparer au seuil de rentabilité arithmétique (cotes du pot) — jamais avant.

**Piège cognitif à surveiller activement, dans ce sens précis** : un seuil de rentabilité bas ("il suffit de 17%") est structurellement plus séduisant à énoncer quand on est déjà engagé dans le coup — c'est une forme de *sunk cost* qui se déguise en calcul froid. Chaque fois qu'une conclusion s'appuie sur un seuil particulièrement bas pour justifier de continuer une ligne déjà entamée, vérifier deux fois la range avant de la présenter comme argument principal.

**Nuance à garder** : ce n'est pas parce que le seuil de rentabilité vient en dernier dans l'ordre de raisonnement qu'il est secondaire — sur une décision proche de l'équilibre, c'est souvent lui qui fait basculer un choix par ailleurs indécis. L'ordre protège contre le biais (ne pas partir du seuil pour justifier une envie), il ne dévalue pas le calcul lui-même.

## Principe

L'équité brute (`equity-engine`) répond à "qui gagne le plus souvent si on allait au tapis maintenant". Une vraie décision de poker dépend aussi de facteurs qui ne rentrent pas dans ce calcul. Ces 5 facteurs sont des heuristiques qualitatives — pas des calculs lourds, pas un solver — à appliquer en plus de l'équité, jamais à sa place.

## 1. Position (IP / OOP)

En position (agir après l'adversaire) permet de mieux **réaliser** son équité brute : contrôle de la taille du pot, information supplémentaire avant de décider, possibilité de checker derrière. Hors position, une partie de l'équité théorique ne se traduit jamais en gains réels.
**Application rapide** : ajuster mentalement l'équité affichée à la hausse si le Héros est en position, à la baisse s'il est hors position — pas de chiffre précis, juste la direction de l'ajustement.

## 2. Implied odds / reverse implied odds

L'équité ne dit pas *comment* elle se matérialise. Une main qui touche rarement mais gagne gros quand elle touche (suited connectors, petites paires pour un set cassé) a de bonnes **implied odds** : les mises futures qu'elle captera en plus du pot actuel. Une main qui touche "à moitié" et se fait sur-payer par mieux (ex : un gros As au kicker faible qui top-paire mais perd contre un meilleur kicker) a des **reverse implied odds** défavorables.
**Application rapide** : suited/connecté/paire = bonnes implied odds. Offsuit avec un seul gros card et un kicker faible = reverse implied odds à surveiller, l'équité brute surestime la vraie valeur de la main.

## 3. SPR (Stack-to-Pot Ratio)

Déjà défini dans `gto-glossary`. Stack profond (SPR élevé) favorise les mains spéculatives à fort potentiel implied odds, qui ont plusieurs rues pour se matérialiser. Stack court (SPR bas) favorise la force brute immédiate — moins de rues restantes pour capitaliser sur l'implied odds.
**Application rapide** : croiser la conclusion des points 2 et 3 — une main spéculative vaut d'autant plus que le SPR est élevé.

## 4. Fold equity / exploitabilité du villain

Une mise ne gagne pas que par showdown — elle peut aussi faire fold l'adversaire avant. Le potentiel de **fold equity** et l'**exploitabilité** d'un adversaire dépendent directement de son profil HUD (déjà utilisé dans `live-session`) :
- Nit / TAG tight : fold equity élevée sur les lignes qui représentent la force, peu exploitable autrement (range déjà proche du GTO).
- Fish / calling station : **fold equity quasi nulle dès le départ, pas seulement "moins bonne"**. La littérature est cohérente là-dessus (GTOWizard, PokerCoaching) : contre un vrai calling station, aucune relance/mise supplémentaire ne "crée" de la fold equity qui n'était pas là — miser deux fois en espérant qu'il finisse par fold est une erreur reconnue, pas une variante légitime. Corollaire : bluffer **une seule fois, tôt, ou pas du tout** contre ce profil ; ne jamais poursuivre un bluff sur une rue suivante dans l'espoir qu'il cède.
- Maniac : fold equity faible, très exploitable en élargissant son propre call/3bet.

**Doctrine à double face contre un loose-passif (Fish/calling station), les deux faces sont nécessaires simultanément** :
- **Élargir** la range d'entrée et le premier call/mise postflop — sa range de continuation initiale est large et son fold equity y est déjà nulle, donc value bet large et bluffe peu dès le départ.
- **Resserrer** franchement l'évaluation de sa range de continuation après qu'il a payé un ou plusieurs **gros** calls consécutifs — "il paie tout" est une simplification qui devient fausse dès qu'il a filtré sa propre range par des mises coûteuses (cf. méthode de range narrowing ci-dessus). Un fish qui a payé 16 puis 38 n'a plus la range qu'il avait au premier call.

**Application rapide** : croiser directement avec le profil HUD du joueur en face avant de conclure sur l'exploitabilité d'une ligne, et re-vérifier ce croisement à *chaque* rue plutôt qu'une fois pour toute la main — un profil ne change pas, mais la range qu'il représente à cet instant précis, si.

## 5. Joueurs restants à parler derrière

Plus il reste de joueurs solides à agir après le Héros, plus le risque de **squeeze**/3bet derrière augmente — ce qui doit resserrer une range d'ouverture ou de call. À l'inverse, être le dernier à parler (ou n'avoir que des joueurs faibles derrière) permet d'élargir.
**Application rapide** : compter les joueurs encore à parler et évaluer leur profil avant de juger une range trop large ou trop tight dans l'absolu.

## Comment l'utiliser

**Constat de session : la formulation "à consulter systématiquement" n'a pas suffi — cette skill n'a été ouverte à aucun moment sur plusieurs analyses approfondies.** Une description de déclenchement ne remplace pas un point d'appel explicite dans le flux de la skill appelante. Concrètement : `live-session` et `hand-review` doivent traiter le passage par cette checklist comme une étape numérotée de leur propre déroulé (elle l'est déjà dans `live-session`, étape 4), pas comme une ressource disponible "si besoin" — la différence entre les deux a été le point de bascule observé.

Ne pas transformer chaque analyse en liste exhaustive des 5 points — les mentionner seulement quand ils changent réellement la conclusion (cohérent avec le principe déjà appliqué pour les folds hors-coup en `live-session` : ne pas noyer l'utilisateur d'information). Mais "ne pas tout citer" ne veut pas dire "ne pas vérifier" : la checklist se parcourt en interne à chaque décision un peu approfondie, seul le résultat filtré apparaît dans la réponse. L'équité reste le point de départ chiffré ; ces 5 facteurs affinent la lecture, dans le vocabulaire de `gto-glossary`.
