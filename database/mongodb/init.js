// ============================================
// MongoDB Initialization Script
// E-Commerce Analytics Platform
// ============================================

// Switch to the ecommerce database
db = db.getSiblingDB('ecommerce');

// ----------------------------------------
// Collections & Indexes
// ----------------------------------------

// Product reviews collection
db.createCollection('product_reviews');
db.product_reviews.createIndex({ product_id: 1 });
db.product_reviews.createIndex({ user_id: 1 });
db.product_reviews.createIndex({ rating: 1 });
db.product_reviews.createIndex({ created_at: -1 });

// User activity / clickstream events
db.createCollection('user_events');
db.user_events.createIndex({ user_id: 1, timestamp: -1 });
db.user_events.createIndex({ event_type: 1 });
db.user_events.createIndex({ session_id: 1 });
db.user_events.createIndex({ timestamp: -1 }, { expireAfterSeconds: 7776000 }); // TTL 90 days

// Product catalog (flexible attributes)
db.createCollection('product_catalog');
db.product_catalog.createIndex({ product_id: 1 }, { unique: true });
db.product_catalog.createIndex({ category: 1, subcategory: 1 });
db.product_catalog.createIndex({ tags: 1 });

// ----------------------------------------
// Seed: Sample Product Reviews
// ----------------------------------------
db.product_reviews.insertMany([
    {
        product_id: 1,
        user_id: 101,
        rating: 5,
        title: "Excellent product!",
        body: "Very happy with my purchase. Would recommend.",
        verified_purchase: true,
        helpful_votes: 12,
        created_at: new Date()
    },
    {
        product_id: 1,
        user_id: 202,
        rating: 4,
        title: "Good value",
        body: "Good quality for the price.",
        verified_purchase: true,
        helpful_votes: 7,
        created_at: new Date()
    },
    {
        product_id: 2,
        user_id: 303,
        rating: 3,
        title: "Average",
        body: "Does the job but nothing special.",
        verified_purchase: false,
        helpful_votes: 2,
        created_at: new Date()
    }
]);

// ----------------------------------------
// Seed: Sample User Events
// ----------------------------------------
db.user_events.insertMany([
    {
        user_id: 101,
        session_id: "sess_abc123",
        event_type: "page_view",
        page: "/products/1",
        timestamp: new Date(),
        device: "desktop",
        browser: "Chrome"
    },
    {
        user_id: 101,
        session_id: "sess_abc123",
        event_type: "add_to_cart",
        product_id: 1,
        quantity: 2,
        timestamp: new Date(),
        device: "desktop",
        browser: "Chrome"
    },
    {
        user_id: 202,
        session_id: "sess_xyz789",
        event_type: "product_search",
        query: "wireless headphones",
        results_count: 24,
        timestamp: new Date(),
        device: "mobile",
        browser: "Safari"
    }
]);

// ----------------------------------------
// Seed: Sample Product Catalog Documents
// ----------------------------------------
db.product_catalog.insertMany([
    {
        product_id: 1,
        product_name: "Wireless Noise-Cancelling Headphones",
        category: "Electronics",
        subcategory: "Audio",
        brand: "SoundWave",
        tags: ["wireless", "bluetooth", "noise-cancelling", "audio"],
        attributes: {
            color: ["Black", "White", "Navy"],
            battery_life_hours: 30,
            connectivity: "Bluetooth 5.0",
            weight_g: 250
        },
        images: [
            "https://example.com/images/headphones_1.jpg"
        ],
        avg_rating: 4.5,
        review_count: 128,
        created_at: new Date()
    },
    {
        product_id: 2,
        product_name: "Organic Cotton T-Shirt",
        category: "Clothing",
        subcategory: "Tops",
        brand: "EcoWear",
        tags: ["organic", "cotton", "sustainable", "casual"],
        attributes: {
            sizes: ["XS", "S", "M", "L", "XL"],
            color: ["White", "Black", "Grey", "Navy"],
            material: "100% Organic Cotton",
            care: "Machine washable"
        },
        images: [
            "https://example.com/images/tshirt_1.jpg"
        ],
        avg_rating: 4.2,
        review_count: 89,
        created_at: new Date()
    }
]);

print("MongoDB initialization complete.");
print("Collections created: product_reviews, user_events, product_catalog");
