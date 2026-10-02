<script lang="ts" module>
  export interface Column {
    key: string;
    label: string;
    align?: "left" | "right" | "center";
    sortable?: boolean;
    phone?: boolean;
    width?: string;
    help?: string;
  }
</script>

<script lang="ts" generics="T">
  // A sortable table that never scrolls sideways on a phone: columns marked `phone: false` show from 640 px up, so a
  // phone keeps the player and two or three numbers. Header taps sort (`onsort`); the sorted column is marked.
  // Numbers align right in tabular figures. Cells come from the `cell` snippet (row, column key, index).
  import type { Snippet } from "svelte";


  let {
    rows,
    columns,
    cell,
    rowKey,
    sort,
    dir = "desc",
    onsort,
    highlight,
    dense = false,
    testid = "table",
  }: {
    rows: T[];
    columns: Column[];
    cell: Snippet<[T, string, number]>;
    rowKey: (r: T, i: number) => string;
    sort?: string;
    dir?: "asc" | "desc";
    onsort?: (key: string) => void;
    highlight?: (r: T) => boolean;
    dense?: boolean;
    testid?: string;
  } = $props();

  const hide = (c: Column) => (c.phone === false ? "hidden sm:table-cell" : "");
  const align = (c: Column) => (c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left");
</script>

<div class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)">
  <table class="w-full table-fixed border-collapse text-base" data-testid={testid}>
    <thead>
      <tr class="border-b border-line bg-raised">
        {#each columns as c (c.key)}
          <th
            class="ll-label px-2 py-2 first:pl-3 last:pr-3 {align(c)} {hide(c)}"
            style={c.width ? `width:${c.width}` : undefined}
            aria-sort={sort === c.key ? (dir === "asc" ? "ascending" : "descending") : undefined}
            title={c.help}
          >
            {#if c.sortable && onsort}
              <button
                type="button"
                class="inline-flex min-h-8 items-center gap-0.5 uppercase {sort === c.key ? 'text-ink' : ''}"
                onclick={() => onsort(c.key)}
                data-testid={`sort-${c.key}`}
                >{c.label}<span aria-hidden="true" class="text-[9px]">{sort === c.key ? (dir === "asc" ? "▲" : "▼") : ""}</span></button
              >
            {:else}
              {c.label}
            {/if}
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as r, i (rowKey(r, i))}
        <tr class="border-b border-line last:border-0 {highlight?.(r) ? 'bg-accent-soft' : ''}" data-testid={`${testid}-row`}>
          {#each columns as c (c.key)}
            <td class="px-2 {dense ? 'py-1.5' : 'py-2'} align-middle first:pl-3 last:pr-3 {align(c)} {hide(c)} {c.align === 'right' ? 'tabnum' : ''}">
              {@render cell(r, c.key, i)}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
