import Link from "next/link";
import type {
  CatalogProduct,
  CategoriesResponse,
  ProductSearchResponse,
} from "../../lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type CatalogPageProps = {
  searchParams: Promise<{
    query?: string;
    category?: string;
    max_price?: string;
    min_rating?: string;
  }>;
};

async function fetchProducts(params: URLSearchParams): Promise<ProductSearchResponse> {
  const response = await fetch(`${API_BASE_URL}/catalog/products?${params.toString()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch products: ${response.status}`);
  }

  return (await response.json()) as ProductSearchResponse;
}

async function fetchCategories(): Promise<CategoriesResponse> {
  const response = await fetch(`${API_BASE_URL}/catalog/categories`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch categories: ${response.status}`);
  }
  return (await response.json()) as CategoriesResponse;
}

function ProductCard({ product }: { product: CatalogProduct }) {
  const offer = product.offers[0];

  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-card-foreground">{product.name}</h3>
          <p className="text-sm text-muted-foreground">
            {product.category.replaceAll("_", " ")} · {product.subcategory.replaceAll("_", " ")}
          </p>
        </div>
        <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-800">
          {product.availability.in_stock ? "In stock" : "Out of stock"}
        </span>
      </div>

      <p className="mt-3 text-sm text-muted-foreground">{product.description}</p>

      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-muted-foreground">Price</p>
          <p className="font-semibold">
            {product.price.currency} {product.price.amount}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Rating</p>
          <p className="font-semibold">
            {product.rating.score} ({product.rating.reviews})
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {product.features.slice(0, 3).map((feature) => (
          <span key={feature} className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">
            {feature.replaceAll("_", " ")}
          </span>
        ))}
      </div>

      {offer ? (
        <p className="mt-3 text-sm font-medium text-emerald-700">
          Offer: {offer.title} ({offer.discount_percent}% off)
        </p>
      ) : null}
    </article>
  );
}

export default async function CatalogPage({ searchParams }: CatalogPageProps) {
  const params = await searchParams;
  const queryParams = new URLSearchParams();

  if (params.query) queryParams.set("query", params.query);
  if (params.category) queryParams.set("category", params.category);
  if (params.max_price) queryParams.set("max_price", params.max_price);
  if (params.min_rating) queryParams.set("min_rating", params.min_rating);
  queryParams.set("limit", "24");

  const [categoriesResult, productsResult] = await Promise.allSettled([
    fetchCategories(),
    fetchProducts(queryParams),
  ]);

  const categories = categoriesResult.status === "fulfilled" ? categoriesResult.value.categories : [];
  const products = productsResult.status === "fulfilled" ? productsResult.value.items : [];
  const total = productsResult.status === "fulfilled" ? productsResult.value.total : 0;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">UrbanRun Catalog Explorer</h1>
          <p className="mt-1 text-xs text-slate-500">
            Complete 113-product deterministic catalog with active offers and real-time inventory.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/buyer"
            className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition shadow-xs"
          >
            Launch AI Buyer &rarr;
          </Link>
        </div>
      </div>

      <form className="mt-6 grid gap-3 rounded-xl border border-border bg-card p-4 md:grid-cols-4">
        <input
          name="query"
          defaultValue={params.query ?? ""}
          placeholder="Search products"
          className="rounded-lg border border-border px-3 py-2 text-sm"
        />

        <select
          name="category"
          defaultValue={params.category ?? ""}
          className="rounded-lg border border-border px-3 py-2 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category.replaceAll("_", " ")}
            </option>
          ))}
        </select>

        <input
          name="max_price"
          type="number"
          min={0}
          defaultValue={params.max_price ?? ""}
          placeholder="Max price"
          className="rounded-lg border border-border px-3 py-2 text-sm"
        />

        <input
          name="min_rating"
          type="number"
          min={0}
          max={5}
          step={0.1}
          defaultValue={params.min_rating ?? ""}
          placeholder="Min rating"
          className="rounded-lg border border-border px-3 py-2 text-sm"
        />

        <button
          type="submit"
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white md:col-span-4"
        >
          Apply filters
        </button>
      </form>

      <div className="mt-6 flex items-center justify-between text-sm text-muted-foreground">
        <span>Showing {products.length} products</span>
        <span>Total matched: {total}</span>
      </div>

      <section className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {products.map((product) => (
          <ProductCard key={product.product_id} product={product} />
        ))}
      </section>

      {productsResult.status === "rejected" ? (
        <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Unable to fetch catalog from backend. Ensure FastAPI is running on port 8000.
        </p>
      ) : null}
    </main>
  );
}
