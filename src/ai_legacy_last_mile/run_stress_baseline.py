"""CLI for the frozen stress baseline."""
import json, os, time
from pathlib import Path
from .llm import OpenAIClient
from .stress_baseline import run

ROOT=Path(__file__).resolve().parents[2]
def main() -> None:
    key=os.environ.get("OPENAI_API_KEY"); model=os.environ.get("OPENAI_MODEL")
    if not key or not model: raise SystemExit("OPENAI_API_KEY and OPENAI_MODEL are required")
    started=time.monotonic(); predictions,raw,failures=run(OpenAIClient(key,model)); out=ROOT/"results"; out.mkdir(exist_ok=True)
    meta={"benchmark_version":"stress-v1.0.0","model":model,"model_calls":20,"failed_calls":len(failures),"runtime_seconds":round(time.monotonic()-started,3),"usage":None,"note":"Usage/cost unavailable from current client telemetry."}
    for name,data in [("stress_baseline_predictions.json",predictions),("stress_baseline_raw.json",{"run":meta,"responses":raw}),("stress_baseline_failures.json",failures)]: (out/name).write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps(meta,indent=2))
if __name__=="__main__": main()
