#!/bin/sh
# Runs the agent against the demo requests and saves each full trace to demo_output/.
# A plain `python agent.py ...` prints only the reflection result and the final answer.
# Run inside the container:  sh run_demo.sh
mkdir -p demo_output
run() {
  name="$1"; emp="$2"; req="$3"
  echo "=== $name ===" | tee "demo_output/$name.txt"
  AGENT_VERBOSE=1 python agent.py "$emp" "$req" 2>&1 | tee -a "demo_output/$name.txt"
}
rm -f demo_output/*.txt
run 1_approve_monitor        E1003 "I need a monitor for my desk."
run 2_deny_too_soon          E1001 "My monitor is flickering, can I get a new monitor?"
run 3_escalate_missing_date  E1004 "My laptop is slow, please replace my laptop."
run 4_escalate_extra_unit    E1001 "I would like a second laptop and I want to keep my current one."
