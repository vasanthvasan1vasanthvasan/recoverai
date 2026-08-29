# RevGuard AI Plan

## Phase Status

1. Scaffold: complete
2. Database: complete
3. Synthetic data: complete
4. Policy engine: complete
5. Diagnosis: complete
6. Razorpay client: complete for Payment Links, pending live credential verification
7. Webhooks: complete
8. Core pipeline: complete
9. Real Razorpay TEST integration: pending credentials and reachable webhook endpoint
10. Subscription extension: pending TEST account capability verification
11. Failure handling: complete for coded fallbacks and tests
12. Batch evaluation: complete
13. Streamlit: complete
14. Testing: ready to run locally after dependency install
15. Documentation: complete

## Remaining Live Verification

- Install dependencies
- Run `pytest`
- Run `python generate_synthetic_data.py`
- Run `python run_evaluation.py`
- Launch `streamlit run app.py`
- If TEST credentials are available, verify a real Payment Link and webhook flow
