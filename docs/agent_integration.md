# Video Job Agent Integration

## Overview

AI agents can create video rendering jobs via the TMCP MCP Bridge's
generic `create_record` tool — **no code changes** to the bridge or agent
framework are required.

## Creating a Video Job via MCP

Use the `create_record` tool with collection `video_jobs`:

```json
{
  "tool": "create_record",
  "arguments": {
    "collection": "video_jobs",
    "data": {
      "workspace_id": "<workspace_id>",
      "requested_by": "marketing_agent",
      "status": "queued",
      "priority": 5,
      "variant_name": "A",
      "input_json": {
        "intro_text": "Top sản phẩm bán chạy",
        "outro_text": "Mua ngay hôm nay!",
        "products": [
          { "image": "product1.jpg", "text": "Sản phẩm 1", "hook": "Giảm 50%" },
          { "image": "product2.jpg", "text": "Sản phẩm 2", "hook": "Mới nhất" }
        ]
      }
    }
  }
}
```

### Fields

| Field          | Required | Description                                      |
| -------------- | -------- | ------------------------------------------------ |
| workspace_id   | yes      | Relation to a workspace                         |
| requested_by   | no       | Agent or user identifier                        |
| status         | yes      | Must be `"queued"` for new jobs                 |
| priority       | no       | 1-10, higher = processed first (default 5)      |
| variant_name   | no       | `"A"`, `"B"`, or `"C"` (default `"A"`)          |
| input_json     | yes      | Content payload (see below)                     |
| input_images   | no       | File field — attach product images              |
| input_music    | no       | File field — custom background music            |
| input_logo     | no       | File field — custom logo overlay                |
| max_attempts   | no       | Max retries before permanent failure (default 3)|
| idempotency_key| no       | Unique key to prevent duplicate jobs            |

### input_json Schema

```json
{
  "intro_text": "string — Text shown in intro hook (required)",
  "outro_text": "string — CTA text in outro (required)",
  "products": [
    {
      "image": "string — filename matching input_images order",
      "text": "string — product name/description",
      "hook": "string — short hook/badge text"
    }
  ]
}
```

- Products: min 2, max 10
- Variant profiles: A (energetic), B (smooth), C (dramatic)

## Checking Job Status

```json
{
  "tool": "get_record",
  "arguments": {
    "collection": "video_jobs",
    "id": "<job_id>"
  }
}
```

Response fields of interest:
- `status`: `queued` → `claimed` → `rendering` → `uploading` → `done` | `failed`
- `progress`: 0-100
- `progress_stage`: current stage description
- `output_video`: filename of rendered MP4 (when `done`)
- `error_message`: failure details (when `failed`)

## Workflow Example

1. Agent collects product data from `products_services` collection
2. Agent uploads images to `media_assets` or directly to job
3. Agent creates `video_jobs` record with `status: "queued"`
4. Worker picks up, renders, uploads MP4
5. Agent polls status or UI shows realtime progress
6. Output video available via PB file URL
