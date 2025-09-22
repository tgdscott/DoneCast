import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { BookText } from 'lucide-react';

export default function StepTemplateSelection({ templates, onTemplateSelect }) {
  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 1: Choose a Template</CardTitle>
      </CardHeader>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {templates.map((template) => (
          <Card
            key={template.id}
            className="cursor-pointer hover:shadow-lg transition-shadow"
            onClick={() => onTemplateSelect(template)}
          >
            <CardContent className="p-6 text-center space-y-4">
              <BookText className="w-12 h-12 mx-auto text-blue-600" />
              <h3 className="text-xl font-semibold">{template.name}</h3>
              <p className="text-gray-500 text-sm">{template.description || 'No description available.'}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
