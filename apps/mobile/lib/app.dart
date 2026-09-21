import 'package:flutter/material.dart';

class FleetManagerApp extends StatelessWidget {
  const FleetManagerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fleet Manager',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B6B5A)),
        useMaterial3: true,
      ),
      home: const FoundationScreen(),
    );
  }
}

class FoundationScreen extends StatelessWidget {
  const FoundationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fleet Manager')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Phase 0 foundation is ready. Driver event actions are intentionally deferred.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
