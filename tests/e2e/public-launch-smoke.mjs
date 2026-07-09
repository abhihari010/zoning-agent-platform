import { chromium } from "playwright";

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:5173";
const mode = process.env.E2E_MODE || "fixture";
const supabaseUserEmail = process.env.E2E_SUPABASE_USER_EMAIL;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
const consoleErrors = [];
const pageErrors = [];

page.on("console", (message) => {
  if (message.type() === "error") {
    consoleErrors.push(message.text());
  }
});
page.on("pageerror", (error) => {
  pageErrors.push(error.message);
});

function jsonResponse(payload, status = 200) {
  return {
    status,
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization, content-type, x-admin-access-key, x-beta-access-key",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  };
}

function analyzePayload(projectId) {
  return {
    status: "complete",
    trace_id: `trace-${projectId}`,
    pipeline: {
      version: "e2e",
      prompt_version: "e2e",
      provider: "fixture",
      rag_provider: "fixture",
      embedding_provider: "fixture",
      trace_id: `trace-${projectId}`,
    },
    trust_indicators: {
      jurisdiction_analyzed: true,
      jurisdiction_supported: true,
      jurisdiction_name: "Blacksburg, VA",
      zoning_district: "General Commercial",
      district_confidence: 0.91,
      source_count: 1,
      citation_count: 1,
      vector_readiness: true,
      last_source_update: "2026-05-25T12:00:00Z",
    },
    citation_validation: {
      valid: true,
      citation_coverage: 1,
      unsupported_claims: [],
      invalid_citation_ids: [],
      confidence_adjustment: "none",
      warnings: [],
      jurisdiction_id: "blacksburg-va",
    },
    agents: [],
    pipeline_stages: [
      {
        key: "intake",
        label: "Understand Project",
        status: "completed",
        headline: "Project facts captured.",
        details: ["Fixture intake completed."],
      },
      {
        key: "location",
        label: "Resolve Property",
        status: "completed",
        headline: "Jurisdiction resolved.",
        details: ["Fixture parcel matched Blacksburg."],
      },
      {
        key: "retrieval",
        label: "Retrieve Sources",
        status: "completed",
        headline: "Sources retrieved.",
        details: ["Fixture source returned."],
      },
      {
        key: "compliance",
        label: "Analyze Compliance",
        status: "completed",
        headline: "Compliance reviewed.",
        details: ["Fixture analysis completed."],
      },
      {
        key: "checklist",
        label: "Generate Checklist",
        status: "completed",
        headline: "Checklist prepared.",
        details: ["Fixture checklist completed."],
      },
    ],
    feasibility: {
      decision: "conditional",
      confidence: 0.82,
      summary: "The fixture project is conditionally supportable in the matched district.",
    },
    compliance: {
      feasibility: "conditional",
      confidence: 0.82,
      summary: "Fixture compliance summary.",
      findings: [
        {
          category: "Use",
          status: "conditional",
          summary: "Confirm use classification with planning staff.",
          citation_ids: ["fixture-source"],
          confidence: 0.8,
        },
      ],
      required_permits: ["Zoning permit"],
      permit_path: "Planning review",
      warnings: [],
      unresolved_questions: [],
      citation_chunk_ids: ["fixture-source:1"],
    },
    checklist: {
      steps: [
        {
          order: 1,
          action: "Confirm zoning permit requirements",
          required_docs: ["Project description", "Site plan"],
          department: "Planning",
        },
      ],
      permits: ["Zoning permit"],
      documents: ["Project description", "Site plan"],
      departments: ["Planning"],
    },
    citations: [
      {
        source_id: "fixture-source",
        title: "Blacksburg Zoning Ordinance",
        excerpt: "Fixture ordinance excerpt for browser smoke.",
        section_ref: "Sec. 100",
        chunk_id: "fixture-source:1",
        jurisdiction_id: "blacksburg-va",
        source_type: "zoning_ordinance",
        url: "https://www.blacksburg.gov/",
        effective_date: "2026-01-01",
        retrieved_at: "2026-05-25T12:00:00Z",
        score: 0.95,
        metadata: {},
      },
    ],
    disclaimers: ["Verify with the official planning office before relying on this result."],
    follow_up_questions: [],
    warnings: [],
  };
}

async function installApiMocks(targetPage) {
  await targetPage.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === "OPTIONS") {
      await route.fulfill(jsonResponse({}));
      return;
    }

    if (path.endsWith("/jurisdictions/coverage")) {
      await route.fulfill(
        jsonResponse({
          jurisdictions: [
            {
              jurisdiction_id: "blacksburg-va",
              name: "Blacksburg, VA",
              state: "VA",
              jurisdiction_type: "municipality",
              coverage_status: "public_supported",
              supported: true,
              official_source_urls: ["https://www.blacksburg.gov/"],
              zoning_map_url: "https://www.blacksburg.gov/",
              planning_contact: { url: "https://www.blacksburg.gov/" },
              last_verified_at: "2026-05-25T12:00:00Z",
            },
            {
              jurisdiction_id: "montgomery-county-va",
              name: "Montgomery County, VA",
              state: "VA",
              jurisdiction_type: "county",
              coverage_status: "public_supported",
              supported: true,
              official_source_urls: ["https://montgomerycountyva.gov/"],
              zoning_map_url: "https://montgomerycountyva.gov/",
              planning_contact: { url: "https://montgomerycountyva.gov/" },
              last_verified_at: "2026-05-25T12:00:00Z",
            },
            {
              jurisdiction_id: "christiansburg-va",
              name: "Christiansburg, VA",
              state: "VA",
              jurisdiction_type: "municipality",
              coverage_status: "source_indexed",
              supported: false,
              official_source_urls: ["https://www.christiansburg.org/"],
              zoning_map_url: "https://www.christiansburg.org/",
              planning_contact: { url: "https://www.christiansburg.org/" },
              last_verified_at: "2026-05-25T12:00:00Z",
            },
          ],
        }),
      );
      return;
    }

    if (path.endsWith("/admin/jurisdiction-requests")) {
      await route.fulfill(
        jsonResponse({
          requests: [
            {
              jurisdiction_id: "christiansburg-va",
              jurisdiction_name: "Christiansburg, VA",
              state: "VA",
              county: "Montgomery County",
              locality: "Christiansburg",
              request_count: 4,
              last_requested_at: "2026-05-25T13:00:00Z",
            },
            {
              jurisdiction_id: "us-va-richmond-city-richmond",
              jurisdiction_name: "Richmond, VA",
              state: "VA",
              county: "Richmond City",
              locality: "Richmond",
              request_count: 2,
              last_requested_at: "2026-05-24T14:00:00Z",
            },
          ],
        }),
      );
      return;
    }

    if (path.endsWith("/me")) {
      await route.fulfill(
        jsonResponse({
          user_id: "e2e-user",
          email: supabaseUserEmail || "e2e@example.com",
          role: "user",
          auth_mode: "disabled",
          public_signups_enabled: true,
        }),
      );
      return;
    }

    if (path.endsWith("/projects")) {
      await route.fulfill(jsonResponse({ projects: [] }));
      return;
    }

    if (path.endsWith("/ingestion/sources")) {
      await route.fulfill(
        jsonResponse({
          sources: [
            {
              source_id: "fixture-source",
              title: "Blacksburg Zoning Ordinance",
              excerpt: "Fixture source excerpt.",
              section_ref: "Sec. 100",
              jurisdiction_id: "blacksburg-va",
              url: "https://www.blacksburg.gov/",
              effective_date: "2026-01-01",
              districts: ["General Commercial"],
              uses: ["Retail or service business"],
            },
          ],
        }),
      );
      return;
    }

    if (path.endsWith("/ingestion/status")) {
      await route.fulfill(
        jsonResponse({
          source_count: 1,
          chunk_count: 1,
          has_index: true,
          index_ready: true,
          auto_seed_sources: true,
          auto_reindex_on_empty: true,
          source_registry_version: "e2e",
          stale_source_ids: [],
          missing_chunk_source_ids: [],
          readiness_warnings: [],
          vector_provider: "fixture",
          vector_index_ready: true,
          vector_count: 1,
          vector_collection: "e2e",
          vector_readiness_warnings: [],
          source_pack_count: 1,
          source_pack_jurisdiction_ids: ["blacksburg-va"],
          last_import_at: "2026-05-25T12:00:00Z",
          last_reindex_at: "2026-05-25T12:00:00Z",
          sources_missing_metadata: [],
        }),
      );
      return;
    }

    if (path.endsWith("/address/suggest")) {
      await route.fulfill(jsonResponse({ suggestions: [] }));
      return;
    }

    if (path.endsWith("/sessions")) {
      await route.fulfill(jsonResponse({ session_id: "00000000-0000-4000-8000-000000000001" }));
      return;
    }

    if (path.endsWith("/projects/intake")) {
      const payload = request.postDataJSON();
      const address = String(payload.address || "").toLowerCase();
      const unsupported = address.includes("christiansburg") || address.includes("richmond");
      await route.fulfill(
        jsonResponse({
          project_id: unsupported
            ? "00000000-0000-4000-8000-000000000003"
            : "00000000-0000-4000-8000-000000000002",
          normalized_address: unsupported
            ? "100 Main St, Christiansburg, VA 24073"
            : "100 Main St, Blacksburg, VA 24060",
          district: unsupported ? "unknown" : "General Commercial",
          place_id: null,
          latitude: unsupported ? 37.1299 : 37.2296,
          longitude: unsupported ? -80.4089 : -80.4139,
          status: "created",
          support_status: unsupported ? "unsupported" : "supported",
          jurisdiction_id: unsupported ? "christiansburg-va" : "blacksburg-va",
          jurisdiction_name: unsupported ? "Christiansburg, VA" : "Blacksburg, VA",
          coverage_status: unsupported ? "source_indexed" : "public_supported",
          planning_contact: { url: "https://www.blacksburg.gov/" },
          official_source_urls: ["https://www.blacksburg.gov/"],
          follow_up_questions: [],
        }),
      );
      return;
    }

    if (path.includes("/projects/") && path.endsWith("/analyze")) {
      if (path.includes("00000000-0000-4000-8000-000000000003")) {
        await route.fulfill(
          jsonResponse(
            {
              detail:
                "Christiansburg, VA is recognized, but source coverage is not ready for zoning review yet.",
            },
            400,
          ),
        );
        return;
      }
      await route.fulfill(jsonResponse(analyzePayload("supported")));
      return;
    }

    if (path.includes("/trace")) {
      await route.fulfill(jsonResponse({ events: [] }));
      return;
    }

    if (path.includes("/projects/") && request.method() === "DELETE") {
      await route.fulfill(jsonResponse({ status: "deleted", project_id: path.split("/").pop() }));
      return;
    }

    if (path.endsWith("/me/data") && request.method() === "DELETE") {
      await route.fulfill(jsonResponse({ status: "deleted", deleted_projects: 1 }));
      return;
    }

    if (path.endsWith("/jurisdiction-requests")) {
      await route.fulfill(
        jsonResponse({
          status: "created",
          jurisdiction_id: "christiansburg-va",
          jurisdiction_name: "Christiansburg, VA",
          request_count: 5,
        }),
      );
      return;
    }

    await route.fulfill(jsonResponse({ detail: `Unhandled e2e route: ${path}` }, 404));
  });
}

function assertNoBrowserErrors() {
  if (pageErrors.length > 0 || consoleErrors.length > 0) {
    throw new Error(
      JSON.stringify(
        {
          pageErrors,
          consoleErrors,
        },
        null,
        2,
      ),
    );
  }
}

async function expectBodyIncludes(...expectedItems) {
  const bodyText = await page.locator("body").innerText({ timeout: 10_000 });
  for (const expected of expectedItems) {
    if (!new RegExp(expected, "i").test(bodyText)) {
      throw new Error(`Page is missing expected copy: ${expected}`);
    }
  }
  return bodyText;
}

async function runWorkspaceFlow() {
  await expectBodyIncludes("Run feasibility review", "Property address");

  const sourceAdmin = page.getByRole("button", { name: "Source admin" });
  if (await sourceAdmin.isVisible().catch(() => false)) {
    await sourceAdmin.click();
    // Admin panels fetch + render async; wait for them rather than snapshotting.
    await page.getByRole("heading", { name: "Source health" }).waitFor({ timeout: 10_000 });
    await page
      .getByRole("heading", { name: "Jurisdiction requests" })
      .waitFor({ timeout: 10_000 });
    await page.getByText("Christiansburg, VA").first().waitFor({ timeout: 10_000 });
    await expectBodyIncludes("Sources indexed");
    await page.getByRole("button", { name: "Review", exact: true }).click();
  }

  await page.locator('input[type="checkbox"]').first().check({ force: true });
  await page
    .getByLabel("Describe the project")
    .fill("Open a small retail studio with customer pickup and light interior work.");
  await page.getByLabel("Property address").fill("100 Main St, Blacksburg, VA");
  await page.getByRole("button", { name: "Run feasibility review" }).click();
  // Dismiss legal disclaimer modal on first run (appears when legal_ack_at not in localStorage)
  const disclaimerModal = page.getByRole("heading", { name: "Disclaimer" });
  if (await disclaimerModal.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await page.getByRole("button", { name: /I understand/i }).click();
  }
  // The determination verdict renders inside the .stamp artifact, not a heading.
  await page.locator(".stamp").getByText("Conditional").waitFor({ timeout: 10_000 });
  await expectBodyIncludes("Blacksburg, VA", "Zoning permit", "Evidence snapshot");

  await page.getByRole("button", { name: "Reset" }).click();
  await page.locator('input[type="checkbox"]').first().check({ force: true });
  await page
    .getByLabel("Describe the project")
    .fill("Open a small bakery with pickup in a jurisdiction that is not public-supported.");
  await page.getByLabel("Property address").fill("100 Main St, Christiansburg, VA");
  await page.getByRole("button", { name: "Run feasibility review" }).click();
  await page.getByText("Request coverage").waitFor({ timeout: 10_000 });
  await expectBodyIncludes("Christiansburg, VA", "Sources indexed", "Request coverage");
}

try {
  if (mode === "fixture") {
    await installApiMocks(page);
  }
  if (mode === "live") {
    // Production: signed-out visitors land on the marketing page; the product
    // workspace sits behind auth at /review.
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
    const bodyText = await page.locator("body").innerText({ timeout: 10_000 });
    if (/three-agent|3 agents/i.test(bodyText)) {
      throw new Error("Old three-agent copy is still visible.");
    }
    const isWorkspace = /Run feasibility review/i.test(bodyText);
    const isLanding = /Know what you can build/i.test(bodyText);
    if (!isWorkspace && !isLanding) {
      throw new Error("Live production page is neither the marketing landing nor the workspace.");
    }
    if (/Source admin|Demand Backlog|Jurisdiction Requests/i.test(bodyText) && !isWorkspace) {
      throw new Error("Signed-out live public surface exposes admin request summary UI.");
    }
    assertNoBrowserErrors();
    console.log(`Public launch live browser smoke passed for ${baseUrl}`);
  } else {
    // Fixture: off Supabase every visitor is treated as authenticated, so the
    // product workspace renders directly at /review.
    await page.goto(new URL("/review", baseUrl).href, {
      waitUntil: "networkidle",
      timeout: 30_000,
    });
    const bodyText = await page.locator("body").innerText({ timeout: 10_000 });
    if (/three-agent|3 agents/i.test(bodyText)) {
      throw new Error("Old three-agent copy is still visible.");
    }
    await runWorkspaceFlow();
    assertNoBrowserErrors();
    console.log(`Public launch browser smoke passed for ${baseUrl}`);
  }
} finally {
  await browser.close();
}
