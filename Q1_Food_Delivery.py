"""Q1 - Food Delivery System: minimal in-memory demo of the HLD flow.
Run: python q1_food_delivery.py
"""
import hashlib
import itertools
import secrets

ORDER_FLOW = ["CREATED", "PAID", "ACCEPTED", "PREPARING", "READY",
              "ASSIGNED", "PICKED_UP", "DELIVERED"]


class UserService:
    def __init__(self):
        self.users, self.tokens = {}, {}

    def register(self, email, password):
        if email in self.users:
            raise ValueError("User already exists")
        self.users[email] = hashlib.sha256(password.encode()).hexdigest()

    def login(self, email, password):
        if self.users.get(email) != hashlib.sha256(password.encode()).hexdigest():
            raise PermissionError("Invalid credentials")
        token = secrets.token_hex(8)  # stands in for a JWT
        self.tokens[token] = email
        return token

    def auth(self, token):
        if token not in self.tokens:
            raise PermissionError("Invalid token")
        return self.tokens[token]


class MenuService:
    def __init__(self):
        self.restaurants = {
            1: {"name": "Pizza Palace", "menu": {101: ("Margherita", 250), 102: ("Farmhouse", 350)}},
            2: {"name": "Biryani House", "menu": {201: ("Chicken Biryani", 300), 202: ("Raita", 50)}},
        }

    def list_restaurants(self):
        return {rid: r["name"] for rid, r in self.restaurants.items()}

    def get_menu(self, rid):
        return self.restaurants[rid]["menu"]


class CartService:
    def __init__(self):
        self.carts = {}  # user -> (restaurant_id, {item_id: qty})

    def add(self, user, rid, item_id, qty=1):
        cart_rid, items = self.carts.get(user, (rid, {}))
        if cart_rid != rid:
            raise ValueError("Cart can hold items from one restaurant only")
        items[item_id] = items.get(item_id, 0) + qty
        self.carts[user] = (rid, items)

    def clear(self, user):
        self.carts.pop(user, None)


class PaymentService:
    def __init__(self):
        self.done = {}  # idempotency_key -> status

    def pay(self, idempotency_key, amount, method="UPI"):
        if idempotency_key in self.done:      # retry never charges twice
            return self.done[idempotency_key]
        self.done[idempotency_key] = "SUCCESS"  # pretend gateway succeeded
        return "SUCCESS"


class OrderService:
    def __init__(self, menu, cart, payment):
        self.menu, self.cart, self.payment = menu, cart, payment
        self.orders, self._id = {}, itertools.count(1)

    def place_order(self, user):
        rid, items = self.cart.carts[user]
        menu = self.menu.get_menu(rid)
        total = sum(menu[i][1] * q for i, q in items.items())
        oid = next(self._id)
        self.orders[oid] = {"user": user, "restaurant": rid, "total": total,
                            "status": "CREATED", "history": ["CREATED"]}
        if self.payment.pay(f"order-{oid}", total) == "SUCCESS":
            self._set(oid, "PAID")
            self.cart.clear(user)
        else:
            self._set(oid, "PAYMENT_FAILED")
        return oid

    def _set(self, oid, status):
        self.orders[oid]["status"] = status
        self.orders[oid]["history"].append(status)
        print(f"  [notify] order {oid} -> {status}")  # Notification Service hook

    def advance(self, oid):
        cur = self.orders[oid]["status"]
        i = ORDER_FLOW.index(cur)
        if i + 1 < len(ORDER_FLOW):
            self._set(oid, ORDER_FLOW[i + 1])

    def track(self, oid):
        return self.orders[oid]["status"]


if __name__ == "__main__":
    users, menu, cart, pay = UserService(), MenuService(), CartService(), PaymentService()
    orders = OrderService(menu, cart, pay)

    users.register("asha@example.com", "secret")
    token = users.login("asha@example.com", "secret")
    user = users.auth(token)

    print("Restaurants:", menu.list_restaurants())
    print("Menu:", menu.get_menu(1))
    cart.add(user, 1, 101, 2)
    cart.add(user, 1, 102, 1)

    oid = orders.place_order(user)
    print("Total:", orders.orders[oid]["total"])
    while orders.track(oid) != "DELIVERED":
        orders.advance(oid)
    print("History:", orders.orders[oid]["history"])
