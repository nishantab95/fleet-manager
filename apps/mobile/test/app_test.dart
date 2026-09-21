import 'package:flutter_test/flutter_test.dart';

import 'package:fleet_manager_mobile/app.dart';

void main() {
  testWidgets('foundation screen renders its scope message', (tester) async {
    await tester.pumpWidget(const FleetManagerApp());

    expect(find.textContaining('Phase 0 foundation'), findsOneWidget);
  });
}
