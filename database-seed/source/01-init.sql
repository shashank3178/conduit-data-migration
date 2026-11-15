-- Customers
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    city VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0
);

-- Orders
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_status VARCHAR(30) NOT NULL DEFAULT 'pending'
);

-- Order items
CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10,2) NOT NULL
);

-- Indexes
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);

-- Sample customers
INSERT INTO customers (full_name, email, city) VALUES
('Aarav Sharma', 'aarav@example.com', 'Indore'),
('Priya Verma', 'priya@example.com', 'Bhopal'),
('Rahul Patel', 'rahul@example.com', 'Mumbai'),
('Ananya Singh', 'ananya@example.com', 'Delhi'),
('Karan Mehta', 'karan@example.com', 'Pune');

-- Sample products
INSERT INTO products (product_name, price, stock_quantity) VALUES
('Laptop', 65000.00, 10),
('Keyboard', 1500.00, 50),
('Mouse', 800.00, 40),
('Monitor', 12000.00, 15),
('Headphones', 2500.00, 20);

-- Sample orders
INSERT INTO orders (customer_id, order_status) VALUES
(1, 'completed'),
(2, 'pending'),
(3, 'completed'),
(1, 'processing'),
(5, 'completed');

-- Sample order items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 65000.00),
(1, 2, 2, 1500.00),
(2, 3, 1, 800.00),
(3, 4, 1, 12000.00),
(4, 5, 2, 2500.00),
(5, 2, 1, 1500.00);