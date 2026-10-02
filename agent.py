import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from equipment.disposition import (
    Investigation,
    describe,
    fact_sheet,
    must_include,
    needs_reflection,
    parse_judgement,
    parse_reflection,
    rule_line,
    unconfirmed_reply,
)
from equipment.errors import ConfigurationError, EquipmentError, ModelError
from equipment.reasons import REPLY_NOT_CONFIRMED, reason_instructions
from equipment.traceability import RunRecord

MAX_STEPS = 10
MAX_TURNS = 14
MAX_GUARDRAIL_STEPS = 6
THOUGHT_LIMIT = 300
JUDGE_THINK = True
JUDGE_UNREADABLE = "The model's judgement of the request could not be read, so a person must decide."
DEFAULT_TIMEOUT = 180
DEFAULT_MODEL = "qwen3:8b"
PROMPTS = Path(__file__).resolve().parent / "prompts"
VERBOSE = os.environ.get("AGENT_VERBOSE") == "1"
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)


def read_prompt(name):
    path = PROMPTS / f"{name}.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ConfigurationError(f"Cannot read prompts/{name}.txt") from error
    if not text:
        raise ConfigurationError(f"prompts/{name}.txt is empty")
    return text


def configured_model():
    return os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def model_hosts():
    configured = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434").strip().rstrip("/")
    hosts = []
    for host in (configured, "http://127.0.0.1:11434"):
        if host and host not in hosts:
            hosts.append(host)
    if not hosts:
        raise ConfigurationError("Set OLLAMA_HOST to the model endpoint.")
    return hosts


def model_timeout():
    raw = os.environ.get("OLLAMA_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        timeout = int(raw)
    except ValueError as error:
        raise ConfigurationError("OLLAMA_TIMEOUT must be a whole number of seconds.") from error
    if timeout <= 0:
        raise ConfigurationError("OLLAMA_TIMEOUT must be greater than zero.")
    return timeout


def tool_text(result):
    content = getattr(result, "content", None)
    if not content:
        return str(result)
    first = content[0]
    return getattr(first, "text", str(first))


def payload_from(result):
    text = tool_text(result)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(data, dict):
        return data
    return {"error": "ToolResult", "message": text}


def tool_schema(tool):
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {})
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    return schema if isinstance(schema, dict) else {}


def tool_listing(listed):
    """One line per tool the server registered: name(parameters): description."""
    lines = []
    for tool in listed.tools:
        params = ", ".join(tool_schema(tool).get("properties", {}))
        lines.append(f"- {tool.name}({params}): {tool.description or ''}")
    return lines


def ollama_tools(listed):
    tools = []
    for tool in listed.tools:
        schema = tool_schema(tool)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": schema,
                },
            }
        )
    return tools


def chat(model, messages, tools, think=False):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"temperature": 0, "num_predict": 3000},
    }
    if tools:
        payload["tools"] = tools
    try:
        body = json.dumps(payload).encode()
    except (TypeError, ValueError) as error:
        raise ModelError("The model request could not be encoded.") from error

    timeout = model_timeout()
    failures = []
    for host in model_hosts():
        request = urllib.request.Request(
            host + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            failures.append(f"{host} returned HTTP {error.code}")
            continue
        except urllib.error.URLError as error:
            failures.append(f"{host} is not reachable ({error.reason})")
            continue
        except TimeoutError:
            failures.append(f"{host} timed out after {timeout}s")
            continue
        except OSError as error:
            failures.append(f"{host} failed ({error})")
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ModelError(f"{host} returned a body that is not JSON.") from error
        message = parsed.get("message") if isinstance(parsed, dict) else None
        if not isinstance(message, dict):
            raise ModelError(f"{host} returned no message.")
        return _without_thinking(message)
    raise ModelError("The model is not reachable. " + "; ".join(failures))


def _without_thinking(message):
    """Qwen thinking stays off. Drop a thinking field or a think block if one still arrives."""
    cleaned = dict(message)
    cleaned.pop("thinking", None)
    content = _THINK_BLOCK.sub("", cleaned.get("content") or "").strip()
    cleaned["content"] = content
    return cleaned


def thought_from(message, name, arguments):
    """The model's stated reason for the call, from the text it wrote with the tool call."""
    text = re.sub(r"^Thought:\s*", "", (message.get("content") or "").strip(), flags=re.I).strip()
    if not text:
        return f"Call {name} with {json.dumps(arguments)}."
    thought = " ".join(text.split())
    if len(thought) > THOUGHT_LIMIT:
        thought = thought[: THOUGHT_LIMIT - 3].rstrip() + "..."
    return thought


def call_arguments(call):
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict) or not function.get("name"):
        raise ModelError("The model returned a tool call without a function name.")
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as error:
            raise ModelError("Tool arguments are not valid JSON.") from error
    if not isinstance(arguments, dict):
        raise ModelError("Tool arguments must be an object.")
    return function["name"], arguments


def read_request():
    if len(sys.argv) == 3:
        employee_id, request_text = sys.argv[1].strip(), sys.argv[2].strip()
    elif len(sys.argv) == 1:
        try:
            employee_id = input("Enter your employee id: ").strip()
            request_text = input("Enter your request: ").strip()
        except EOFError as error:
            raise ConfigurationError("Employee id and request are required.") from error
    else:
        raise ConfigurationError("Usage: python agent.py <employee_id> <request>")
    if not employee_id or not request_text:
        raise ConfigurationError("Employee id and request are required.")
    return employee_id, request_text


def _show(*lines):
    if VERBOSE:
        print("\n".join(lines))
        print()


def _record(trace, *lines):
    block = "\n".join(lines)
    _show(block)
    trace.append(block)


def _finish(record, trace, final, verdict=None, reflection="", draft=""):
    """Print only the outcome. The full trace goes to the traceability log."""
    record.add("\n".join(trace))
    if draft:
        record.add("draft: " + draft)
    if verdict:
        print("Reflection:", verdict)
        record.add(f"reflection: {verdict}. {reflection}".strip())
    print("Final answer:")
    print(final)
    record.finish(final)


def _record_step(trace, label, thought, name, arguments, observation):
    _record(
        trace,
        label,
        f"Thought: {thought}",
        f"Action: {name}",
        f"Action Input: {json.dumps(arguments)}",
        f"Observation: {observation}",
    )


async def _call_tool(session, name, arguments):
    try:
        result = await session.call_tool(name, arguments=arguments)
    except Exception as error:
        return {"error": type(error).__name__, "message": str(error)}, json.dumps(
            {"error": type(error).__name__, "message": str(error)}
        )
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        payload = payload_from(result)
        if "error" not in payload:
            payload = {"error": "ToolError", "message": tool_text(result)}
        return payload, json.dumps(payload)
    payload = payload_from(result)
    return payload, tool_text(result)


async def _escalate_unconfirmed(session, investigation, trace, why):
    """Send the request to a person instead of returning a reply that failed reflection."""
    arguments = {
        "employee_id": investigation.employee.get("employee_id") or investigation.employee_id,
        "request": investigation.request,
        "reason": REPLY_NOT_CONFIRMED,
    }
    payload, observation = await _call_tool(session, "flag_for_human_review", arguments)
    _record_step(
        trace,
        "Reflection escalation",
        f"{why} The agent escalates instead of sending a decision it could not confirm.",
        "flag_for_human_review",
        arguments,
        observation,
    )
    return unconfirmed_reply(investigation.employee, payload)


def judgement_question(template, investigation):
    return template.replace("{allowed}", "\n".join(investigation.allowance_lines())).replace(
        "{request}", investigation.request
    )


async def _judge(model, session, investigation, trace, messages, template):
    """Ask the model whether the employee's words fit what the policy allows; escalate if not."""
    ask = [{"role": "user", "content": judgement_question(template, investigation)}]
    verdict = None
    for _ in range(2):
        try:
            content = (chat(model, ask, None, think=JUDGE_THINK).get("content") or "").strip()
            _record(trace, "Judgement answer:\n" + content)
        except ModelError:
            break
        verdict = parse_judgement(content)
        if verdict:
            break
        ask += [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Answer on one line that starts with ESCALATE: or CLEAR:."},
        ]
    kind, reason = verdict or ("escalate", JUDGE_UNREADABLE)

    if kind == "clear":
        _record(trace, f"Judgement: CLEAR. {reason}".strip())
        messages.append(
            {"role": "user", "content": "Your judgement of the employee's words: CLEAR. The rule results stand as they are."}
        )
        return

    arguments = {
        "employee_id": investigation.employee.get("employee_id") or investigation.employee_id,
        "request": investigation.request,
        "reason": reason,
    }
    problem = investigation.call_problem("flag_for_human_review", arguments)
    if problem:
        _record(trace, f"Judgement: ESCALATE ({reason}), but the flag was not run: {problem}")
        return
    payload, observation = await _call_tool(session, "flag_for_human_review", arguments)
    if not payload.get("error"):
        investigation.observe("flag_for_human_review", payload, arguments)
    _record_step(trace, "Judgement", reason, "flag_for_human_review", arguments, observation)
    messages.append(
        {"role": "user", "content": f"Your judgement: ESCALATE. Observation from flag_for_human_review: {observation}"}
    )


async def _decide(model, employee_id, request_text, record):
    system = read_prompt("system") + "\n\n" + reason_instructions()
    decide_now = read_prompt("decide_now")
    judge = read_prompt("judge")
    reflect = read_prompt("reflect")
    server_path = str(Path(__file__).resolve().parent / "server.py")
    server = StdioServerParameters(command=sys.executable, args=[server_path])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = ollama_tools(listed)
            names = {tool.name for tool in listed.tools}
            if not names:
                raise ConfigurationError("The server registered no tools.")

            listing = tool_listing(listed)
            _show("Tools from the MCP server:", *listing)
            record.add("tools:\n" + "\n".join(listing))
            _show(f"Model: {model}", f"Employee: {employee_id}", f"Request: {request_text}")

            investigation = Investigation(employee_id, request_text)
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"Employee id: {employee_id}\n"
                        f"Request: {request_text}\n"
                        "Investigate with the tools, then give the decision."
                    ),
                },
            ]

            steps = 0
            turns = 0
            trace = []
            while steps < MAX_STEPS and turns < MAX_TURNS:
                turns += 1
                message = chat(model, messages, tools)
                calls = message.get("tool_calls") or []
                if not isinstance(calls, list):
                    raise ModelError("The model returned tool_calls that are not a list.")

                if not calls:
                    content = (message.get("content") or "").strip()
                    missing = investigation.missing_step()
                    if missing is None:
                        break
                    note = f"The investigation is not finished. Still needed: {missing}."
                    _record(trace, f"Guardrail: the model answered without a tool call. {note}")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": note + " Call that tool now."})
                    continue

                messages.append(
                    {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls}
                )
                for call in calls:
                    if steps >= MAX_STEPS:
                        break
                    steps += 1
                    payload = None
                    try:
                        name, arguments = call_arguments(call)
                    except ModelError as error:
                        name, arguments = "invalid_tool_call", {}
                        thought = str(error)
                        observation = json.dumps({"error": "ModelError", "message": str(error)})
                    else:
                        thought = thought_from(message, name, arguments)
                        problem = (
                            f"Unknown tool {name}." if name not in names
                            else investigation.call_problem(name, arguments)
                        )
                        if problem:
                            observation = json.dumps({"error": "NotRun", "message": problem})
                        else:
                            payload, observation = await _call_tool(session, name, arguments)
                            if not payload.get("error"):
                                investigation.observe(name, payload, arguments)
                    _record_step(trace, f"Step {steps} of {MAX_STEPS}", thought, name, arguments, observation)
                    messages.append({"role": "tool", "tool_name": name, "content": observation})
                    check = investigation.rule_check(name, arguments, payload)
                    if check:
                        _record(trace, check)
                        messages.append({"role": "user", "content": check})

            guardrail_steps = 0
            while guardrail_steps < MAX_GUARDRAIL_STEPS:
                step = investigation.next_action()
                if step is None:
                    break
                guardrail_steps += 1
                name, arguments = step
                payload, observation = await _call_tool(session, name, arguments)
                investigation.observe(name, payload, arguments)
                _record_step(
                    trace,
                    f"Guardrail step {guardrail_steps}",
                    f"The model stopped before {describe(step)}, which the rules require, so the agent makes the call.",
                    name,
                    arguments,
                    observation,
                )
                messages.append({"role": "user", "content": f"Observation from {name}: {observation}"})
                check = investigation.rule_check(name, arguments, payload)
                if check:
                    _record(trace, check)
                    messages.append({"role": "user", "content": check})

            if investigation.incomplete_reason():
                _finish(record, trace, investigation.reply())
                return

            if investigation.needs_judgement():
                await _judge(model, session, investigation, trace, messages, judge)

            for decision in investigation.decisions():
                _record(trace, "Thought: " + decision["rationale"])

            decisions = investigation.decisions()
            if not needs_reflection(decisions):
                _finish(
                    record,
                    trace,
                    investigation.reply(),
                    verdict="skipped",
                    reflection="Every item was escalated by a data rule, so the reply is the stored review record.",
                )
                return

            facts = fact_sheet(investigation.employee, decisions, investigation.reviews)
            fact_block = "\n".join(f"- {fact}" for fact in facts)
            rule_block = "\n".join(f"- {rule_line(decision)}" for decision in decisions)
            must_block = "\n".join(
                f"- {entry}" for entry in must_include(investigation.employee, investigation.reviews)
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"{decide_now}\n\nRule results:\n{rule_block}\n\nFacts:\n{fact_block}",
                }
            )
            try:
                drafted = chat(model, messages, None)
            except ModelError as error:
                reflection = f"The model could not draft a reply ({error}), so there was nothing to check."
                final = await _escalate_unconfirmed(session, investigation, trace, reflection)
                _finish(record, trace, final, verdict="not match", reflection=reflection)
                return

            draft = (drafted.get("content") or "").strip()
            _show("Draft: " + (draft or "(the model returned an empty draft)"))

            matched, reflection = None, "The model returned an empty draft."
            if draft:
                check = (
                    reflect.replace("{request}", investigation.request)
                    .replace("{rules}", rule_block)
                    .replace("{facts}", fact_block)
                    .replace("{must_include}", must_block)
                    .replace("{draft}", draft)
                )
                try:
                    verdict = chat(model, [{"role": "user", "content": check}], None).get("content") or ""
                    _record(trace, "Reflection check:\n" + verdict.strip())
                except ModelError as error:
                    verdict = ""
                    _record(trace, f"Reflection call failed: {error}")
                matched, reflection = parse_reflection(verdict)
                if matched is None:
                    reflection = "The model's verdict on the draft could not be read."

            final = draft
            if not matched:
                final = await _escalate_unconfirmed(session, investigation, trace, reflection)
            _finish(
                record,
                trace,
                final,
                verdict="match" if matched else "not match",
                reflection=reflection,
                draft=draft,
            )


async def main(employee_id, request_text):
    model = configured_model()
    record = RunRecord(employee_id, request_text, model=model)
    try:
        await _decide(model, employee_id, request_text, record)
    except Exception as error:
        record.add(f"error: {type(error).__name__}: {error}")
        record.finish(str(error), status="failed")
        raise


if __name__ == "__main__":
    try:
        employee_id, request_text = read_request()
        asyncio.run(main(employee_id, request_text))
    except EquipmentError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        raise SystemExit(130) from None
