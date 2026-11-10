# Matrice de traçabilité — TireTwin-QA

Révision `37e8435` — générée le 2026-11-10.

- 8 exigences : 7 vérifiées, 1 limitation(s) connue(s), 0 en échec, 0 non couverte(s) ou incomplète(s).
- 19 tests de validation liés à une exigence.
- 67 autres tests (unitaires, outillage) : 67 réussis, 0 en échec.

## Synthèse par exigence

| Exigence | Intitulé | Tests | Verdict |
|---|---|---|---|
| REQ-001 | Détection d'une perte de pression | 4/4 | ✅ Réussi |
| REQ-002 | Absence de fausse alerte en roulage nominal | 1/1 | ✅ Réussi |
| REQ-003 | Robustesse aux virages serrés et aux freinages | 1/1 | ✅ Réussi |
| REQ-004 | Perte de communication CAN | 1/1 | ✅ Réussi |
| REQ-005 | Équivalence avec l'implémentation de référence | 9/9 | ✅ Réussi |
| REQ-006 | Budget de temps de calcul | 1/1 | ✅ Réussi |
| REQ-007 | Sous-gonflage simultané des quatre pneus | 0/1 | ⚠️ Limitation connue |
| REQ-008 | Recalibration après changement de pneu | 1/1 | ✅ Réussi |

## Détail exigence ↔ test ↔ résultat

| Exigence | Test | Scénario | Résultat | Mesures |
|---|---|---|---|---|
| REQ-001 | `Requirements/Detection.FaultyWheelIsFlaggedWithinTheDeadline/REQ_001_loss20_fl` | loss20_fl | ✅ Réussi | detection_delay_s=14.20 |
| REQ-001 | `Requirements/Detection.FaultyWheelIsFlaggedWithinTheDeadline/REQ_001_loss20_fr` | loss20_fr | ✅ Réussi | detection_delay_s=14.22 |
| REQ-001 | `Requirements/Detection.FaultyWheelIsFlaggedWithinTheDeadline/REQ_001_loss20_rl` | loss20_rl | ✅ Réussi | detection_delay_s=14.38 |
| REQ-001 | `Requirements/Detection.FaultyWheelIsFlaggedWithinTheDeadline/REQ_001_loss20_rr` | loss20_rr | ✅ Réussi | detection_delay_s=13.88 |
| REQ-002 | `Requirements/NoWarning.NoWarningOverTheWholeScenario/REQ_002_nominal_30min` | nominal_30min | ✅ Réussi | usable_ratio=0.79 |
| REQ-003 | `Requirements/NoWarning.NoWarningOverTheWholeScenario/REQ_003_corner_brake` | corner_brake | ✅ Réussi | usable_ratio=0.57 |
| REQ-004 | `Requirements/Unavailable.OutageIsSignalledAndSurvived/REQ_004_can_dropout` | can_dropout | ✅ Réussi |  |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_nominal_30min` | nominal_30min | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_loss20_fl` | loss20_fl | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_loss20_fr` | loss20_fr | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_loss20_rl` | loss20_rl | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_loss20_rr` | loss20_rr | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_corner_brake` | corner_brake | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_can_dropout` | can_dropout | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_all_four_minus20` | all_four_minus20 | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-005 | `Requirements/BackToBack.CppMatchesThePythonReference/REQ_005_tyre_change_reset` | tyre_change_reset | ✅ Réussi | max_abs_error_pct=0.0e+00 |
| REQ-006 | `Requirements/StepTime.StepFitsInTheComputationBudget/REQ_006_nominal_30min` | nominal_30min | ✅ Réussi | mean_step_us=0.048, p99_step_us=0.100 |
| REQ-007 | `Requirements/KnownLimitation.DesiredBehaviourIsNotMetYet/REQ_007_all_four_minus20` | all_four_minus20 | ⚠️ Échec attendu |  |
| REQ-008 | `Requirements/Reset.ResetClearsTheWarningAndRelearnsTheReference/REQ_008_tyre_change_reset` | tyre_change_reset | ✅ Réussi |  |
