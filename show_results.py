import json

d = json.load(open('sentence_test_80plus_results.json', encoding='utf-8'))

lines = []
lines.append("="*80)
lines.append(f"Overall Accuracy: {d['overall_accuracy']*100:.1f}%")
lines.append(f"Deployment Ready: {d['deployment_ready']}")
lines.append(f"Sentences >=80%: {d['sentences_above_80pct']} / {d['total_sentences']}")
lines.append(f"Avg Confidence: {d['avg_confidence']:.4f}")
lines.append(f"Breakdown: perfect={d['breakdown']['perfect']} good={d['breakdown']['good']} fair={d['breakdown']['fair']} poor={d['breakdown']['poor']}")
lines.append("")

for r in d['per_sentence']:
    lines.append(f"KALIMAT {r['sentence_id']}: {r['accuracy']*100:.0f}% | {r['kalimat']}")
    for det in r['details']:
        ok = 'BENAR' if det['correct'] else 'SALAH'
        lines.append(f"  [{ok}] {det['target']:20s} -> {det['predicted']:20s} conf={det['confidence']:.4f}")

lines.append("")
lines.append("="*80)
lines.append("TARGET >80% TERCAPAI!" if d['sentences_above_80pct'] == d['total_sentences'] else "BELUM TERCAPAI")

report = "\n".join(lines)
print(report)

# Save as text too
with open("sentence_test_report.txt", "w", encoding="utf-8") as f:
    f.write(report)
print("\nReport saved to sentence_test_report.txt")
