#!/usr/bin/env python3
"""Build shared gold eval_data.yaml (trace-free) for RHIDP-14578 (≤150 turns)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "dataset" / "eval_data.yaml"

DRY_RUN_YAML = """apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: mcp-eval-dry-run
  title: MCP Eval Dry Run
spec:
  type: service
  parameters: []
  steps:
    - id: noop
      name: Noop
      action: debug:log
      input:
        message: mcp-eval-dry-run
"""


def turn(
    turn_id: str,
    query: str,
    expected_tool_calls: Any,
    expected_response: str,
    expected_intent: str | None = None,
) -> dict[str, Any]:
    t: dict[str, Any] = {
        "turn_id": turn_id,
        "query": query,
        "expected_tool_calls": expected_tool_calls,
        "expected_response": expected_response,
    }
    if expected_intent:
        t["expected_intent"] = expected_intent
    return t


def conv(
    cid: str,
    description: str,
    tag: str,
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "conversation_group_id": cid,
        "description": description,
        "tag": tag,
        "turns": turns,
    }


def qce(arguments: dict[str, Any] | None = None) -> list[list[dict[str, Any]]]:
    return [
        [
            {
                "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                "arguments": arguments or {},
            }
        ]
    ]


def alt_tools(*tool_specs: tuple[str, dict[str, Any]]) -> list[Any]:
    """Multiple alternative single-step patterns."""
    return [[[{"tool_name": name, "arguments": args}]] for name, args in tool_specs]


def build() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []

    # ── catalog (~45) ───────────────────────────────────────────────
    kinds = [
        ("API", "APIs", "list APIs from the catalog"),
        ("Component", "Components", "list Components from the catalog"),
        ("Resource", "Resources", "list Resources from the catalog"),
        ("Group", "Groups", "list Groups from the catalog"),
        ("User", "Users", "list Users from the catalog"),
        ("System", "Systems", "list Systems from the catalog"),
        ("Domain", "Domains", "list Domains from the catalog"),
        ("Location", "Locations", "list Locations from the catalog"),
    ]
    data.append(
        conv(
            "catalog-list-all",
            "List catalog entities with no filters",
            "catalog",
            [
                turn(
                    "list_all",
                    "Retrieve all entries in the Backstage Catalog",
                    qce({}),
                    "A summary of catalog entities returned by an unfiltered catalog query.",
                    "list or summarize catalog entities using a catalog query tool",
                )
            ],
        )
    )
    for kind, plural, intent in kinds:
        data.append(
            conv(
                f"catalog-filter-kind-{kind.lower()}",
                f"Filter catalog by kind {kind}",
                "catalog",
                [
                    turn(
                        f"filter_{kind.lower()}",
                        f"Show me all {plural} in the catalog",
                        qce({"kind": kind}),
                        f"Lists {plural} from the catalog filtered by kind={kind}.",
                        intent,
                    )
                ],
            )
        )

    owners = [
        ("payments-team", "payments-team"),
        ("security-team", "security-team"),
        ("accounts-team", "accounts-team"),
        ("open-banking-team", "open-banking-team"),
        ("compliance-team", "compliance-team"),
        ("event-team", "event-team"),
    ]
    for owner, label in owners:
        data.append(
            conv(
                f"catalog-filter-owner-{owner}",
                f"Filter catalog by owner {owner}",
                "catalog",
                [
                    turn(
                        "filter_owner",
                        f"Find catalog entities owned by {label}. "
                        f"Call query-catalog-entities with owner set to a value containing {owner}.",
                        qce({"owner": f".*{owner}.*"}),
                        f"Lists catalog entities owned by {owner}.",
                        f"find catalog entities owned by {owner}",
                    )
                ],
            )
        )

    tags = ["payments", "consent", "database", "security", "ais", "pis"]
    for tag in tags:
        data.append(
            conv(
                f"catalog-filter-tags-{tag}",
                f"Filter catalog by tag {tag}",
                "catalog",
                [
                    turn(
                        "filter_tags",
                        f"Show catalog entities tagged with {tag}",
                        qce({"tags": tag}),
                        f"Lists catalog entities that include the tag {tag}.",
                        f"find catalog entities tagged with {tag}",
                    )
                ],
            )
        )

    type_filters = [
        ("Component", "service", "service Components"),
        ("Component", "website", "website Components"),
        ("API", "openapi", "OpenAPI APIs"),
        ("Resource", "database", "database Resources"),
    ]
    for kind, typ, label in type_filters:
        data.append(
            conv(
                f"catalog-filter-{kind.lower()}-{typ}",
                f"Filter {kind} by type {typ}",
                "catalog",
                [
                    turn(
                        "filter_kind_type",
                        f"Find {kind}s of type {typ} in the catalog",
                        qce({"kind": kind, "type": typ}),
                        f"Lists {label} from the catalog.",
                        f"find {label} in the catalog",
                    )
                ],
            )
        )

    entities = [
        "consent-management-api",
        "payment-initiation-api",
        "standing-orders-api",
        "beneficiary-management-api",
        "account-access-api",
        "balance-check-api",
        "transaction-history-api",
        "webhook-notifications-api",
    ]
    for name in entities:
        data.append(
            conv(
                f"catalog-get-entity-{name}",
                f"Fetch entity {name}",
                "catalog",
                [
                    turn(
                        "get_entity",
                        f"Get the catalog entity named {name}",
                        [
                            [
                                {
                                    "tool_name": "catalog.get-catalog-entity",
                                    "arguments": {"name": name},
                                }
                            ]
                        ],
                        f"Returns details for the catalog entity {name}.",
                        f"retrieve the {name} catalog entity",
                    )
                ],
            )
        )

    data.append(
        conv(
            "catalog-model-description",
            "Catalog model description",
            "catalog",
            [
                turn(
                    "model_description",
                    "Describe the catalog model and what entity kinds are registered",
                    [
                        [
                            {
                                "tool_name": "catalog.get-catalog-model-description",
                                "arguments": {},
                            }
                        ]
                    ],
                    "Describes the Backstage catalog model and registered entity kinds.",
                    "describe the Backstage catalog model / entity kinds",
                )
            ],
        )
    )

    # ── techdocs (~20) ──────────────────────────────────────────────
    data.append(
        conv(
            "techdocs-list",
            "List entities with TechDocs",
            "techdocs",
            [
                turn(
                    "fetch_techdocs",
                    "Which entities have TechDocs documentation available?",
                    alt_tools(
                        ("techdocs-mcp-extras.fetch-techdocs", {}),
                        ("techdocs-mcp-extras.analyze-techdocs-coverage", {}),
                    ),
                    "Reports which catalog entities have TechDocs, or that none are indexed.",
                    "report which entities have TechDocs available",
                )
            ],
        )
    )
    data.append(
        conv(
            "techdocs-coverage",
            "TechDocs coverage overall",
            "techdocs",
            [
                turn(
                    "coverage",
                    "What is our TechDocs documentation coverage across catalog entities?",
                    [
                        [
                            {
                                "tool_name": "techdocs-mcp-extras.analyze-techdocs-coverage",
                                "arguments": {},
                            }
                        ]
                    ],
                    "Reports TechDocs coverage statistics across the catalog.",
                    "report TechDocs documentation coverage across the catalog",
                )
            ],
        )
    )
    for owner in ["payments-team", "security-team", "accounts-team", "compliance-team"]:
        data.append(
            conv(
                f"techdocs-coverage-owner-{owner}",
                f"TechDocs coverage for {owner}",
                "techdocs",
                [
                    turn(
                        "coverage_owner",
                        f"Analyze TechDocs coverage for entities owned by {owner}",
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.analyze-techdocs-coverage",
                                    "arguments": {"owner": f".*{owner}.*"},
                                }
                            ]
                        ],
                        f"Reports TechDocs coverage for entities owned by {owner}.",
                        f"report TechDocs coverage for {owner} owned entities",
                    )
                ],
            )
        )
    for et in ["Component", "API", "System", "Resource"]:
        data.append(
            conv(
                f"techdocs-fetch-{et.lower()}",
                f"Fetch TechDocs for {et}",
                "techdocs",
                [
                    turn(
                        "fetch_typed",
                        f"List TechDocs for {et} entities only",
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.fetch-techdocs",
                                    "arguments": {"entityType": et},
                                }
                            ]
                        ],
                        f"Lists TechDocs associated with {et} entities (may be empty).",
                        f"list TechDocs for {et} entities",
                    )
                ],
            )
        )
    data.append(
        conv(
            "techdocs-retrieve-home",
            "Retrieve TechDocs content when possible",
            "techdocs",
            [
                turn(
                    "retrieve_home",
                    "If any entity has TechDocs, retrieve the content of its documentation home page; "
                    "otherwise say none are available after checking.",
                    [
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.fetch-techdocs",
                                    "arguments": {},
                                }
                            ],
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.retrieve-techdocs-content",
                                    "arguments": {"entityRef": ".*"},
                                }
                            ],
                        ],
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.fetch-techdocs",
                                    "arguments": {},
                                }
                            ]
                        ],
                    ],
                    "Retrieves TechDocs home content for an entity, or reports none available.",
                    "find TechDocs entities and retrieve documentation content when available",
                )
            ],
        )
    )

    # ── scaffolder-read (~20) ───────────────────────────────────────
    data.append(
        conv(
            "scaffolder-list-templates",
            "List software templates",
            "scaffolder-read",
            [
                turn(
                    "fetch_templates",
                    "What software templates are available in the scaffolder?",
                    [
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.fetch-template-metadata",
                                "arguments": {},
                            }
                        ]
                    ],
                    "Lists available software templates (fixture may return none).",
                    "list available software templates",
                )
            ],
        )
    )
    for name in [
        "example-nodejs-template",
        "react-ssr-template",
        "docs-template",
        "mcp-eval-dry-run",
    ]:
        data.append(
            conv(
                f"scaffolder-template-{name}",
                f"Fetch template metadata for {name}",
                "scaffolder-read",
                [
                    turn(
                        "template_by_name",
                        f"Get metadata for the software template named {name} if it exists",
                        [
                            [
                                {
                                    "tool_name": "scaffolder-mcp-extras.fetch-template-metadata",
                                    "arguments": {"name": name},
                                }
                            ]
                        ],
                        f"Returns metadata for template {name}, or indicates it was not found.",
                        f"fetch metadata for template {name}",
                    )
                ],
            )
        )

    data.append(
        conv(
            "scaffolder-list-actions",
            "List scaffolder actions",
            "scaffolder-read",
            [
                turn(
                    "list_actions",
                    "List all installed Scaffolder actions",
                    alt_tools(
                        ("scaffolder-mcp-extras.list-scaffolder-actions", {}),
                        ("scaffolder.list-scaffolder-actions", {}),
                    ),
                    "Lists installed scaffolder action IDs and descriptions.",
                    "list installed scaffolder actions",
                )
            ],
        )
    )
    data.append(
        conv(
            "scaffolder-list-tasks",
            "List scaffolder tasks",
            "scaffolder-read",
            [
                turn(
                    "list_tasks",
                    "Show recent scaffolder tasks",
                    alt_tools(
                        ("scaffolder-mcp-extras.list-scaffolder-tasks", {}),
                        ("scaffolder-mcp-extras.list-scaffolder-tasks", {"limit": ".*"}),
                        ("scaffolder.list-scaffolder-tasks", {}),
                        ("scaffolder.list-scaffolder-tasks", {"limit": ".*"}),
                    ),
                    "Lists recent scaffolder tasks and their statuses.",
                    "list recent scaffolder tasks",
                )
            ],
        )
    )
    for limit in ["5", "10", "20"]:
        data.append(
            conv(
                f"scaffolder-list-tasks-limit-{limit}",
                f"List scaffolder tasks with limit {limit}",
                "scaffolder-read",
                [
                    turn(
                        "list_tasks_limit",
                        f"Show the {limit} most recent scaffolder tasks",
                        alt_tools(
                            (
                                "scaffolder-mcp-extras.list-scaffolder-tasks",
                                {"limit": limit},
                            ),
                            ("scaffolder.list-scaffolder-tasks", {"limit": limit}),
                            ("scaffolder-mcp-extras.list-scaffolder-tasks", {}),
                            ("scaffolder.list-scaffolder-tasks", {}),
                        ),
                        f"Lists up to {limit} recent scaffolder tasks.",
                        "list recent scaffolder tasks",
                    )
                ],
            )
        )

    # ── scaffolder-write (~8) dry-run only ───────────────────────────
    for i in range(1, 6):
        data.append(
            conv(
                f"scaffolder-write-validate-{i}",
                "Sandbox-safe dry-run validation (execute-template skipped — no Templates in fixture)",
                "scaffolder-write",
                [
                    turn(
                        "validate_minimal",
                        "Validate this scaffolder template by dry-running it. "
                        "Prefer scaffolder-mcp-extras.validate-scaffolder "
                        "(or scaffolder.dry-run-template). Do not execute a real scaffolder task. "
                        f"Pass templateYaml as the following YAML document (variant {i}):\n\n"
                        + DRY_RUN_YAML,
                        alt_tools(
                            (
                                "scaffolder-mcp-extras.validate-scaffolder",
                                {"templateYaml": "(?s).*mcp-eval-dry-run.*"},
                            ),
                            (
                                "scaffolder.dry-run-template",
                                {"templateYaml": "(?s).*mcp-eval-dry-run.*"},
                            ),
                        ),
                        "Dry-runs/validates the provided template YAML without creating a scaffolder task.",
                        "dry-run/validate the provided scaffolder template without executing a real task",
                    )
                ],
            )
        )

    # ── multi_step (~15) ────────────────────────────────────────────
    multi_owners = ["payments-team", "security-team", "accounts-team"]
    for owner in multi_owners:
        data.append(
            conv(
                f"multi-components-then-coverage-{owner}",
                f"Components then TechDocs coverage for {owner}",
                "multi_step",
                [
                    turn(
                        "components_then_coverage",
                        f"List Components owned by {owner}, then analyze TechDocs coverage for that same owner",
                        [
                            [
                                {
                                    "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                    "arguments": {
                                        "kind": "Component",
                                        "owner": f".*{owner}.*",
                                    },
                                }
                            ],
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.analyze-techdocs-coverage",
                                    "arguments": {"owner": f".*{owner}.*"},
                                }
                            ],
                        ],
                        f"Lists Components for {owner} and reports their TechDocs coverage.",
                        f"list {owner} Components then analyze their TechDocs coverage",
                    )
                ],
            )
        )
        data.append(
            conv(
                f"multi-apis-then-owner-entities-{owner}",
                f"APIs then all entities for {owner}",
                "multi_step",
                [
                    turn(
                        "apis_then_owner",
                        f"First list all APIs in the catalog, then find all catalog entities owned by {owner}",
                        [
                            [
                                {
                                    "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                    "arguments": {"kind": "API"},
                                }
                            ],
                            [
                                {
                                    "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                    "arguments": {"owner": f".*{owner}.*"},
                                }
                            ],
                        ],
                        f"Lists APIs, then entities owned by {owner}.",
                        f"list APIs then list entities owned by {owner}",
                    )
                ],
            )
        )

    data.append(
        conv(
            "multi-techdocs-then-content",
            "Fetch TechDocs then retrieve content if present",
            "multi_step",
            [
                turn(
                    "fetch_then_retrieve",
                    "Find an entity that has TechDocs and retrieve the content of its documentation home page",
                    [
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.fetch-techdocs",
                                    "arguments": {},
                                }
                            ],
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.retrieve-techdocs-content",
                                    "arguments": {"entityRef": ".*"},
                                }
                            ],
                        ],
                        [
                            [
                                {
                                    "tool_name": "techdocs-mcp-extras.fetch-techdocs",
                                    "arguments": {},
                                }
                            ]
                        ],
                    ],
                    "Fetches TechDocs entities and retrieves content when available.",
                    "find TechDocs entities and retrieve documentation content when available",
                )
            ],
        )
    )
    data.append(
        conv(
            "multi-templates-then-actions",
            "List templates then list actions",
            "multi_step",
            [
                turn(
                    "templates_then_actions",
                    "List available software templates, then list all installed scaffolder actions",
                    [
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.fetch-template-metadata",
                                "arguments": {},
                            }
                        ],
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.list-scaffolder-actions",
                                "arguments": {},
                            }
                        ],
                    ],
                    "Lists templates and then installed scaffolder actions.",
                    "list templates then list scaffolder actions",
                )
            ],
        )
    )
    data.append(
        conv(
            "multi-entity-then-model",
            "Get entity then catalog model",
            "multi_step",
            [
                turn(
                    "entity_then_model",
                    "Get the catalog entity named consent-management-api, then describe the catalog model",
                    [
                        [
                            {
                                "tool_name": "catalog.get-catalog-entity",
                                "arguments": {"name": "consent-management-api"},
                            }
                        ],
                        [
                            {
                                "tool_name": "catalog.get-catalog-model-description",
                                "arguments": {},
                            }
                        ],
                    ],
                    "Fetches consent-management-api then describes the catalog model.",
                    "retrieve consent-management-api then describe the catalog model",
                )
            ],
        )
    )

    # ── negative (~25) ──────────────────────────────────────────────
    data.append(
        conv(
            "negative-no-execute-template",
            "Inspect templates only — must not execute",
            "negative",
            [
                turn(
                    "inspect_only",
                    "I only want to inspect available templates. Do not create or execute anything.",
                    [
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.fetch-template-metadata",
                                "arguments": {},
                            }
                        ]
                    ],
                    "Inspects templates without executing or creating scaffolder tasks.",
                    "inspect templates only without creating or executing a scaffolder task",
                )
            ],
        )
    )
    data.append(
        conv(
            "negative-empty-filter-type",
            "Unlikely type filter — empty OK",
            "negative",
            [
                turn(
                    "empty_filter",
                    "Find catalog Components of type definitely-does-not-exist-xyz",
                    qce(
                        {
                            "kind": "Component",
                            "type": "definitely-does-not-exist-xyz",
                        }
                    ),
                    "Queries the catalog and reports no matching Components for that type.",
                    "query the catalog with an unlikely filter and report empty or no matching results",
                )
            ],
        )
    )
    data.append(
        conv(
            "negative-empty-filter-tag",
            "Unlikely tag filter — empty OK",
            "negative",
            [
                turn(
                    "empty_tag",
                    "Show catalog entities tagged with zz-no-such-tag-999",
                    qce({"tags": "zz-no-such-tag-999"}),
                    "Queries the catalog and reports no entities for that tag.",
                    "query the catalog with an unlikely tag and report empty results",
                )
            ],
        )
    )
    data.append(
        conv(
            "negative-empty-owner",
            "Unlikely owner filter — empty OK",
            "negative",
            [
                turn(
                    "empty_owner",
                    "Find catalog entities owned by no-such-team-xyz-999",
                    qce({"owner": ".*no-such-team-xyz-999.*"}),
                    "Queries the catalog and reports no entities for that owner.",
                    "query the catalog for a non-existent owner and report empty results",
                )
            ],
        )
    )
    for bad_name in [
        "definitely-missing-entity-xyz",
        "no-such-api-abc",
        "ghost-component-000",
    ]:
        data.append(
            conv(
                f"negative-missing-entity-{bad_name}",
                f"Missing entity {bad_name}",
                "negative",
                [
                    turn(
                        "missing_entity",
                        f"Get the catalog entity named {bad_name}",
                        [
                            [
                                {
                                    "tool_name": "catalog.get-catalog-entity",
                                    "arguments": {"name": bad_name},
                                }
                            ]
                        ],
                        f"Attempts to fetch {bad_name} and reports it was not found or unavailable.",
                        f"attempt to retrieve missing entity {bad_name}",
                    )
                ],
            )
        )

    # Wrong-tool traps: gold expects catalog query, not scaffolder execute
    data.append(
        conv(
            "negative-no-register-on-list",
            "Listing catalog must not register entities",
            "negative",
            [
                turn(
                    "list_not_register",
                    "Just list Components in the software catalog. Do not register or unregister anything.",
                    qce({"kind": "Component"}),
                    "Lists Components without registering or unregistering entities.",
                    "list Components without mutating the catalog",
                )
            ],
        )
    )
    data.append(
        conv(
            "negative-docs-not-execute",
            "Docs question must not execute templates",
            "negative",
            [
                turn(
                    "docs_not_execute",
                    "What is our TechDocs coverage? Do not run any scaffolder templates.",
                    [
                        [
                            {
                                "tool_name": "techdocs-mcp-extras.analyze-techdocs-coverage",
                                "arguments": {},
                            }
                        ]
                    ],
                    "Reports TechDocs coverage without executing scaffolder templates.",
                    "report TechDocs coverage without executing templates",
                )
            ],
        )
    )

    # Ambiguous / precision cases
    data.append(
        conv(
            "negative-owner-not-team-rewrite",
            "Owner must be payments-team not rewritten",
            "negative",
            [
                turn(
                    "owner_exactish",
                    "Find catalog entities owned by payments-team. "
                    "Use owner payments-team (not a rewritten form like team-payments).",
                    qce({"owner": ".*payments-team.*"}),
                    "Lists entities owned by payments-team using the correct owner filter.",
                    "find catalog entities owned by payments-team",
                )
            ],
        )
    )

    # Extra catalog precision / lifecycle-style filters (fixture-aware)
    for kind, owner in [
        ("Component", "payments-team"),
        ("API", "payments-team"),
        ("Component", "security-team"),
        ("API", "security-team"),
        ("Resource", "payments-team"),
        ("API", "accounts-team"),
        ("Component", "accounts-team"),
        ("Resource", "accounts-team"),
    ]:
        data.append(
            conv(
                f"catalog-{kind.lower()}-owner-{owner}",
                f"{kind} owned by {owner}",
                "catalog",
                [
                    turn(
                        "kind_owner",
                        f"List {kind} entities owned by {owner}",
                        qce({"kind": kind, "owner": f".*{owner}.*"}),
                        f"Lists {kind} entities owned by {owner}.",
                        f"list {kind} entities owned by {owner}",
                    )
                ],
            )
        )

    for tag, kind in [
        ("payments", "Component"),
        ("payments", "API"),
        ("consent", "API"),
        ("consent", "Component"),
        ("database", "Resource"),
    ]:
        data.append(
            conv(
                f"catalog-{kind.lower()}-tag-{tag}",
                f"{kind} tagged {tag}",
                "catalog",
                [
                    turn(
                        "kind_tag",
                        f"Show {kind} entities tagged with {tag}",
                        qce({"kind": kind, "tags": tag}),
                        f"Lists {kind} entities tagged {tag}.",
                        f"list {kind} entities tagged with {tag}",
                    )
                ],
            )
        )

    # More negative traps
    for q, tool, args, exp, intent, cid in [
        (
            "Do not use the scaffolder. Only query the catalog for Resources.",
            "software-catalog-mcp-extras.query-catalog-entities",
            {"kind": "Resource"},
            "Lists Resources via catalog query without using scaffolder tools.",
            "list Resources without using scaffolder tools",
            "negative-resources-no-scaffolder",
        ),
        (
            "Summarize TechDocs coverage only. Do not list scaffolder tasks.",
            "techdocs-mcp-extras.analyze-techdocs-coverage",
            {},
            "Reports TechDocs coverage without listing scaffolder tasks.",
            "report TechDocs coverage without listing scaffolder tasks",
            "negative-coverage-no-tasks",
        ),
        (
            "List scaffolder actions only. Do not execute or dry-run any template.",
            "scaffolder-mcp-extras.list-scaffolder-actions",
            {},
            "Lists scaffolder actions without dry-running or executing templates.",
            "list scaffolder actions without validating or executing templates",
            "negative-actions-no-dryrun",
        ),
    ]:
        data.append(
            conv(
                cid,
                cid,
                "negative",
                [
                    turn(
                        "trap",
                        q,
                        [[[{"tool_name": tool, "arguments": args}]]],
                        exp,
                        intent,
                    )
                ],
            )
        )

    # Additional multi-step
    data.append(
        conv(
            "multi-tag-then-owner",
            "Tag filter then owner filter",
            "multi_step",
            [
                turn(
                    "tag_then_owner",
                    "Show catalog entities tagged with payments, then find entities owned by payments-team",
                    [
                        [
                            {
                                "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                "arguments": {"tags": "payments"},
                            }
                        ],
                        [
                            {
                                "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                "arguments": {"owner": ".*payments-team.*"},
                            }
                        ],
                    ],
                    "Lists payments-tagged entities, then payments-team owned entities.",
                    "list payments-tagged entities then payments-team owned entities",
                )
            ],
        )
    )
    data.append(
        conv(
            "multi-actions-then-tasks",
            "List actions then tasks",
            "multi_step",
            [
                turn(
                    "actions_then_tasks",
                    "List installed scaffolder actions, then show recent scaffolder tasks",
                    [
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.list-scaffolder-actions",
                                "arguments": {},
                            }
                        ],
                        [
                            {
                                "tool_name": "scaffolder-mcp-extras.list-scaffolder-tasks",
                                "arguments": {},
                            }
                        ],
                    ],
                    "Lists scaffolder actions and then recent tasks.",
                    "list scaffolder actions then list recent tasks",
                )
            ],
        )
    )
    for name in ["payment-initiation-api", "standing-orders-api"]:
        data.append(
            conv(
                f"multi-get-{name}-then-owner-components",
                f"Get {name} then list owner components",
                "multi_step",
                [
                    turn(
                        "get_then_components",
                        f"Get the catalog entity named {name}, then list Components owned by payments-team",
                        [
                            [
                                {
                                    "tool_name": "catalog.get-catalog-entity",
                                    "arguments": {"name": name},
                                }
                            ],
                            [
                                {
                                    "tool_name": "software-catalog-mcp-extras.query-catalog-entities",
                                    "arguments": {
                                        "kind": "Component",
                                        "owner": ".*payments-team.*",
                                    },
                                }
                            ],
                        ],
                        f"Fetches {name} then lists payments-team Components.",
                        f"retrieve {name} then list payments-team Components",
                    )
                ],
            )
        )

    return data


def main() -> None:
    data = build()
    turns = sum(len(c["turns"]) for c in data)
    if turns > 150:
        raise SystemExit(f"Gold has {turns} turns; plan allows ≤150")
    header = """# RHDH MCP golden set (RHIDP-14578 full campaign).
# Shared gold only — no tool_calls/response/contexts here.
# Prefer overlay tools (*-mcp-extras.*) over upstream duplicates.
# Fixture: mcp-integrations demo catalog (payments-team, security-team, etc.).
# Template kind count is 0 → execute-template skipped; write path uses dry-run validate.
# TechDocs may be empty locally; multi-step retrieve is optional when fetch is empty.
# Per-model traces live under evaluation-result/<model>/evaluation_dataset_*.yaml

"""
    OUT.write_text(
        header
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    )
    by_tag: dict[str, int] = {}
    for c in data:
        by_tag[c["tag"]] = by_tag.get(c["tag"], 0) + len(c["turns"])
    print(f"Wrote {OUT} conversations={len(data)} turns={turns}")
    print("by_tag", by_tag)


if __name__ == "__main__":
    main()
